"""Studio views for pre-submit validation API."""

from __future__ import annotations

import json
import uuid

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .entity_permissions import MANAGE_FORMS_WRITE
from .manage_capabilities import studio_capability_required
from .manage_views import _form_for_manage
from .models import FormSubmitValidationConfig
from .outbound.http_client import redact_headers, send_json_integration_post
from .submit_validation.messages import applicant_validation_message, extract_api_message
from .submit_validation.payload import build_pre_submit_validation_payload, wrap_validation_payload
from .submit_validation.runner import _config_ready
from .submit_validation_forms import FormSubmitValidationConfigForm


def _get_or_create_config(form_instance) -> FormSubmitValidationConfig:
    config, _ = FormSubmitValidationConfig.objects.get_or_create(form=form_instance)
    return config


@studio_capability_required(MANAGE_FORMS_WRITE)
def form_submit_validation(request, pk):
    form_instance = _form_for_manage(request, pk)
    config = _get_or_create_config(form_instance)
    test_result = None

    if request.method == "POST":
        config_form = FormSubmitValidationConfigForm(request.POST, instance=config)
        if config_form.is_valid():
            config_form.save()
            messages.success(request, _("Validate by API settings saved."))
            return redirect("manage:form_submit_validation", pk=form_instance.pk)
    else:
        config_form = FormSubmitValidationConfigForm(instance=config)

    return render(
        request,
        "magicforms/manage/form_submit_validation.html",
        {
            "form_obj": form_instance,
            "config": config,
            "config_form": config_form,
            "test_result": test_result,
            "payload_preview_keys": (
                "phase",
                "validated_at",
                "form",
                "entity",
                "submitter_email",
                "fields",
            ),
            "message_placeholders": "{{status}}, {{api_message}}",
        },
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def form_submit_validation_test(request, pk):
    form_instance = _form_for_manage(request, pk)
    config = _get_or_create_config(form_instance)
    if not _config_ready(config):
        messages.error(
            request,
            _("Turn on Active, set the endpoint URL, and save (plus API secret when required)."),
        )
        return redirect("manage:form_submit_validation", pk=pk)

    fields_def = list(form_instance.get_ordered_fields())
    body = build_pre_submit_validation_payload(
        form_instance,
        {},
        fields_def,
        request=request,
    )
    for ff in fields_def:
        body["fields"][ff.name] = "(sample)"
    payload = wrap_validation_payload(config, body)
    url = (config.endpoint_url or "").strip()

    try:
        status, raw, redacted, _sent = send_json_integration_post(
            config,
            url=url,
            payload=payload,
            extra_headers={
                "X-MagicForms-Validation": "1",
                "X-MagicForms-Test": "1",
                "X-MagicForms-Form-Id": str(form_instance.pk),
            },
            idempotency_key=str(uuid.uuid4()),
        )
        ok = 200 <= status < 300
        test_result = {
            "ok": ok,
            "status_code": status,
            "response_body": raw[:2000],
            "request_headers_display": json.dumps(redacted, indent=2),
        }
        if ok:
            messages.success(
                request,
                _("Test call returned HTTP %(status)s — submissions would be accepted.") % {"status": status},
            )
        else:
            messages.warning(
                request,
                _("Test call returned HTTP %(status)s — check failure action settings.") % {"status": status},
            )
    except ConnectionError as exc:
        test_result = {"ok": False, "error": str(exc)}
        messages.error(request, _("Could not reach the validation endpoint: %(err)s") % {"err": exc})
    except Exception:
        messages.error(request, _("Test request failed."))
        return redirect("manage:form_submit_validation", pk=pk)

    return render(
        request,
        "magicforms/manage/form_submit_validation.html",
        {
            "form_obj": form_instance,
            "config": config,
            "config_form": FormSubmitValidationConfigForm(instance=config),
            "test_result": test_result,
            "payload_preview_keys": (
                "phase",
                "validated_at",
                "form",
                "entity",
                "submitter_email",
                "fields",
            ),
            "message_placeholders": "{{status}}, {{api_message}}",
        },
    )
