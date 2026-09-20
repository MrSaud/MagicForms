"""Studio views for per-form outbound POST integration."""

from __future__ import annotations

import json
import uuid

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .entity_permissions import MANAGE_FORMS_WRITE
from .manage_capabilities import studio_capability_required
from .manage_views import _form_for_manage
from .models import FormOutboundConfig, FormOutboundDelivery
from .outbound.dispatch import TRIGGER_SUBMITTED
from .outbound.payload import build_outbound_payload
from .outbound.testing import (
    build_health_check_payload,
    build_sample_payload,
    config_test_readiness,
    default_custom_test_json,
    parse_custom_test_payload,
    run_outbound_test,
)
from .outbound.worker import process_delivery
from .outbound_forms import (
    OUTBOUND_FIELD_MAP_MAX_NUM,
    FormOutboundConfigForm,
    FormOutboundFieldMapFormSet,
)

_SESSION_TEST_KEY = "outbound_test_{form_pk}"
_SESSION_CUSTOM_JSON_KEY = "outbound_test_custom_json_{form_pk}"


def _get_or_create_config(form_instance) -> FormOutboundConfig:
    config, _ = FormOutboundConfig.objects.get_or_create(form=form_instance)
    return config


def _store_test_result(request, form_pk: int, result: dict) -> None:
    request.session[_SESSION_TEST_KEY.format(form_pk=form_pk)] = result
    request.session.modified = True


def _get_test_result(request, form_pk: int) -> dict | None:
    raw = request.session.get(_SESSION_TEST_KEY.format(form_pk=form_pk))
    return raw if isinstance(raw, dict) else None


def _clear_test_results(request, form_pk: int) -> None:
    key = _SESSION_TEST_KEY.format(form_pk=form_pk)
    if key in request.session:
        del request.session[key]
        request.session.modified = True


def _redirect_outbound_test(pk: int):
    return redirect(reverse("manage:form_outbound", kwargs={"pk": pk}) + "#mf-outbound-test-result")


def _wants_json_test_response(request) -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _enrich_test_result(result: dict) -> dict:
    enriched = dict(result)
    headers = enriched.get("request_headers")
    if headers:
        try:
            enriched["request_headers_display"] = json.dumps(headers, indent=2)
        except (TypeError, ValueError):
            enriched["request_headers_display"] = ""
    else:
        enriched["request_headers_display"] = enriched.get("request_headers_display") or ""
    return enriched


def _respond_outbound_test(
    request,
    form_pk: int,
    result: dict | None,
    *,
    error: str | None = None,
    http_status: int = 400,
    flash_info: bool = False,
) -> JsonResponse | redirect:
    if error:
        if _wants_json_test_response(request):
            return JsonResponse({"ok": False, "error": error}, status=http_status)
        if flash_info:
            messages.info(request, error)
        else:
            messages.error(request, error)
        return _redirect_outbound_test(form_pk)
    assert result is not None
    result = _enrich_test_result(result)
    _store_test_result(request, form_pk, result)
    if _wants_json_test_response(request):
        return JsonResponse({"ok": bool(result.get("ok")), "result": result})
    _flash_test_result(request, result)
    return _redirect_outbound_test(form_pk)


def _flash_test_result(request, result: dict) -> None:
    kind = result.get("kind", "test")
    labels = {
        "health_check": _("API health check"),
        "sample_payload": _("Sample POST"),
        "custom_json": _("Custom JSON POST"),
        "submitted": _("Submission POST"),
    }
    label = labels.get(kind, _("Test"))
    if result.get("ok"):
        messages.success(
            request,
            _("%(label)s succeeded (HTTP %(code)s).") % {
                "label": label,
                "code": result.get("status"),
            },
        )
    else:
        messages.error(
            request,
            _("%(label)s failed: %(err)s") % {
                "label": label,
                "err": result.get("error") or _("unknown"),
            },
        )


@studio_capability_required(MANAGE_FORMS_WRITE)
def form_outbound(request, pk):
    form_instance = _form_for_manage(request, pk)
    config = _get_or_create_config(form_instance)
    form_fields = list(form_instance.get_ordered_fields())

    config_locked = config.is_active

    if request.method == "POST":
        if config_locked:
            if request.POST.get("is_active") == "on":
                messages.error(
                    request,
                    _(
                        "This integration is active. Turn off Active and save to edit "
                        "connection, triggers, or field mappings."
                    ),
                )
                return redirect("manage:form_outbound", pk=form_instance.pk)
            config.is_active = False
            config.save(update_fields=["is_active"])
            _clear_test_results(request, form_instance.pk)
            messages.success(
                request,
                _("Integration deactivated. You can now edit and save settings."),
            )
            return redirect("manage:form_outbound", pk=form_instance.pk)

        config_form = FormOutboundConfigForm(
            request.POST,
            instance=config,
            form_instance=form_instance,
        )
        map_formset = FormOutboundFieldMapFormSet(
            request.POST,
            instance=config,
            form_kwargs={"form_fields": form_fields},
            prefix="maps",
        )
        if config_form.is_valid() and map_formset.is_valid():
            with transaction.atomic():
                config = config_form.save()
                map_formset.instance = config
                for obj in map_formset.save(commit=False):
                    if (obj.external_key or "").strip():
                        obj.config = config
                        obj.save()
                for obj in map_formset.deleted_objects:
                    obj.delete()
            _clear_test_results(request, form_instance.pk)
            messages.success(request, _("Outbound integration saved."))
            return redirect("manage:form_outbound", pk=form_instance.pk)
    else:
        config_form = FormOutboundConfigForm(instance=config, form_instance=form_instance)
        map_formset = FormOutboundFieldMapFormSet(
            instance=config,
            form_kwargs={"form_fields": form_fields},
            prefix="maps",
        )
        if not config.field_maps.exists():
            map_formset.extra = 5

    if config_locked:
        for name, field in config_form.fields.items():
            if name != "is_active":
                field.disabled = True
        for map_form in map_formset.forms:
            for field in map_form.fields.values():
                field.disabled = True

    recent_deliveries = (
        FormOutboundDelivery.objects.filter(config=config)
        .select_related("submission")
        .order_by("-created_at")[:25]
    )
    mapping_saved_count = config.field_maps.count()
    ready, readiness_message = config_test_readiness(config)
    test_result = _get_test_result(request, form_instance.pk)
    if test_result:
        test_result = _enrich_test_result(test_result)

    return render(
        request,
        "magicforms/manage/form_outbound.html",
        {
            "form_obj": form_instance,
            "config": config,
            "config_locked": config_locked,
            "config_form": config_form,
            "map_formset": map_formset,
            "recent_deliveries": recent_deliveries,
            "mapping_max": OUTBOUND_FIELD_MAP_MAX_NUM,
            "mapping_saved_count": mapping_saved_count,
            "mapping_form_count": len(map_formset.forms),
            "test_ready": ready,
            "test_readiness_message": readiness_message,
            "test_result": test_result,
            "has_submissions": form_instance.submissions.exists(),
            "test_custom_json": request.session.get(
                _SESSION_CUSTOM_JSON_KEY.format(form_pk=form_instance.pk)
            )
            or default_custom_test_json(config, form_instance),
        },
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def form_outbound_test_custom(request, pk):
    form_instance = _form_for_manage(request, pk)
    config = get_object_or_404(FormOutboundConfig, form=form_instance)
    raw_body = request.POST.get("json_body", "")
    request.session[_SESSION_CUSTOM_JSON_KEY.format(form_pk=form_instance.pk)] = raw_body
    request.session.modified = True

    payload, err = parse_custom_test_payload(config, raw_body)
    if payload is None:
        return _respond_outbound_test(request, pk, None, error=err)

    result = run_outbound_test(
        config,
        form_id=form_instance.pk,
        payload=payload,
        trigger="custom_json",
        submission_ref="CUSTOM",
    )
    return _respond_outbound_test(request, pk, result)


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def form_outbound_test_health(request, pk):
    form_instance = _form_for_manage(request, pk)
    config = get_object_or_404(FormOutboundConfig, form=form_instance)
    payload = build_health_check_payload(form_instance.pk)
    result = run_outbound_test(
        config,
        form_id=form_instance.pk,
        payload=payload,
        trigger="health_check",
        submission_ref="HEALTH",
    )
    return _respond_outbound_test(request, pk, result)


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def form_outbound_test_sample(request, pk):
    form_instance = _form_for_manage(request, pk)
    config = get_object_or_404(FormOutboundConfig, form=form_instance)
    payload = build_sample_payload(config, form_instance)
    result = run_outbound_test(
        config,
        form_id=form_instance.pk,
        payload=payload,
        trigger="sample_payload",
        submission_ref="SAMPLE",
    )
    return _respond_outbound_test(request, pk, result)


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def form_outbound_test_submission(request, pk):
    """POST using the latest real submission and saved field mappings."""
    form_instance = _form_for_manage(request, pk)
    config = get_object_or_404(FormOutboundConfig, form=form_instance)
    ready, msg = config_test_readiness(config)
    if not ready:
        return _respond_outbound_test(request, pk, None, error=msg)
    submission = form_instance.submissions.order_by("-submitted_at").first()
    if submission is None:
        return _respond_outbound_test(
            request,
            pk,
            None,
            error=_("Add at least one submission to run this test."),
            flash_info=True,
        )

    try:
        payload = build_outbound_payload(
            config,
            submission,
            trigger=TRIGGER_SUBMITTED,
            request=request,
        )
    except ValueError as exc:
        return _respond_outbound_test(request, pk, None, error=str(exc))

    result = run_outbound_test(
        config,
        form_id=form_instance.pk,
        payload=payload,
        trigger=TRIGGER_SUBMITTED,
        submission_ref=submission.reference_token,
    )

    if result.get("ok"):
        delivery = FormOutboundDelivery.objects.create(
            config=config,
            submission=submission,
            trigger=TRIGGER_SUBMITTED,
            idempotency_key=result.get("event_id") or str(uuid.uuid4()),
            status=FormOutboundDelivery.Status.SUCCESS,
            attempt_count=1,
            request_url=result.get("request_url", ""),
            request_headers_redacted=json.dumps(result.get("request_headers") or {}),
            request_body_redacted=(result.get("request_body") or "")[:8000],
            response_status=result.get("status"),
            response_body_truncated=(result.get("response") or "")[:4000],
            completed_at=timezone.now(),
        )
        delivery.save()

    return _respond_outbound_test(request, pk, result)


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def form_outbound_retry(request, pk, delivery_id):
    form_instance = _form_for_manage(request, pk)
    config = get_object_or_404(FormOutboundConfig, form=form_instance)
    delivery = get_object_or_404(
        FormOutboundDelivery,
        pk=delivery_id,
        config=config,
    )
    delivery.status = FormOutboundDelivery.Status.PENDING
    delivery.next_retry_at = timezone.now()
    delivery.error_message = ""
    delivery.save(update_fields=["status", "next_retry_at", "error_message"])
    process_delivery(delivery)
    delivery.refresh_from_db()
    if delivery.status == FormOutboundDelivery.Status.SUCCESS:
        messages.success(request, _("Delivery succeeded."))
    else:
        messages.error(
            request,
            _("Delivery failed: %(err)s") % {"err": delivery.error_message or _("unknown")},
        )
    return redirect("manage:form_outbound", pk=pk)
