"""Mobile API: applicant pending related (child) forms."""

from __future__ import annotations

from uuid import UUID

from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404

from magicforms.api.mobile_form_submit import (
    _field_errors_from_form,
    _form_submit_status,
    _request_for_mapping,
    _serialize_field,
    _serialize_initial_value,
    _status_message,
)
from magicforms.dynamic_forms import build_public_form, build_visibility_rules
from magicforms.models import FieldType, FormSubmission, SubmissionEvent, SupplementarySubmission
from magicforms.notification_emails import queue_after_submission_event
from magicforms.supplementary import record_related_child_submitted, respondent_may_access_related_form
from magicforms.user_mapping import build_initial_from_mappings
from magicforms.api.mobile_content import serialize_published_form, _iso_dt, _dt_label
from magicforms.i18n_db import gettext_db
from django.db import transaction


def _mobile_user(request: HttpRequest):
    return getattr(request, "mobile_user", None)


def _get_supplementary_row(request: HttpRequest, access_token: str) -> SupplementarySubmission:
    user = _mobile_user(request)
    try:
        token_uuid = UUID(str(access_token).strip())
    except ValueError:
        raise Http404
    row = get_object_or_404(
        SupplementarySubmission.objects.select_related(
            "link__child_form",
            "link__child_form__entity",
            "link__child_form__submit_validation_config",
            "parent_submission",
            "parent_submission__submitted_by",
            "parent_submission__form",
            "child_submission",
        ),
        access_token=token_uuid,
    )
    if row.parent_submission.submitted_by_id != user.pk:
        raise Http404
    if row.child_submission_id:
        raise Http404
    child = row.link.child_form
    if not child.is_published or child.deleted_at is not None:
        raise Http404
    return row


def pending_related_payload(request: HttpRequest) -> dict:
    user = _mobile_user(request)
    rows = list(
        SupplementarySubmission.objects.filter(
            parent_submission__submitted_by=user,
            child_submission__isnull=True,
            link__child_form__is_published=True,
            link__child_form__deleted_at__isnull=True,
        )
        .select_related(
            "link__child_form",
            "link__child_form__entity",
            "parent_submission__form",
        )
        .order_by("-invited_at", "id")
    )
    items = []
    for row in rows:
        child = row.link.child_form
        parent = row.parent_submission
        items.append(
            {
                "access_token": str(row.access_token),
                "invited_at": _iso_dt(row.invited_at),
                "invited_at_label": _dt_label(row.invited_at),
                "child_form": {
                    "id": child.pk,
                    "title": child.title,
                    "slug": child.slug,
                    "entity_slug": child.entity.slug,
                    "entity_name": child.entity.name,
                },
                "parent_submission": {
                    "id": parent.pk,
                    "reference_token": parent.reference_token or "",
                    "form_title": parent.form.title,
                },
            }
        )
    return {"total": len(items), "items": items}


def related_form_schema_payload(request: HttpRequest, access_token: str) -> dict:
    row = _get_supplementary_row(request, access_token)
    child = row.link.child_form
    user = _mobile_user(request)
    parent = row.parent_submission

    if not respondent_may_access_related_form(_request_for_mapping(user), parent):
        return {
            "status": "denied",
            "status_message": "You cannot complete this related form.",
        }

    fields_def = list(child.get_ordered_fields())
    sections = [
        {
            "id": s.pk,
            "title": gettext_db(s.title),
            "description": gettext_db(s.description) if s.description else "",
            "starts_collapsed": s.starts_collapsed,
            "order": s.order,
        }
        for s in child.get_ordered_sections()
    ]
    FormClass = build_public_form(child)
    initial_raw = build_initial_from_mappings(_request_for_mapping(user), fields_def)
    initial = {
        key: _serialize_initial_value(
            next(ff for ff in fields_def if f"f_{ff.pk}" == key),
            val,
        )
        for key, val in initial_raw.items()
    }
    status = _form_submit_status(child, user)

    from magicforms.api.submit_validation_meta import submit_validation_meta_for_form

    return {
        "form": serialize_published_form(request, child),
        "related": {
            "access_token": str(row.access_token),
            "parent_form_title": parent.form.title,
            "parent_reference_token": parent.reference_token or "",
        },
        "status": status,
        "status_message": _status_message(status, child),
        "sections": sections,
        "fields": [_serialize_field(ff) for ff in fields_def],
        "initial": initial,
        "visibility_rules": build_visibility_rules(fields_def),
        "submit_validation": submit_validation_meta_for_form(child),
    }


def related_form_submit_payload(request: HttpRequest, access_token: str) -> tuple[dict, int]:
    row = _get_supplementary_row(request, access_token)
    child = row.link.child_form
    user = _mobile_user(request)
    parent = row.parent_submission

    if not respondent_may_access_related_form(_request_for_mapping(user), parent):
        return (
            {
                "ok": False,
                "error": "access_denied",
                "message": "You cannot complete this related form.",
            },
            403,
        )

    status = _form_submit_status(child, user)
    if status != "open":
        return (
            {
                "ok": False,
                "error": "form_not_accepting",
                "message": _status_message(status, child),
                "status": status,
            },
            400,
        )

    FormClass = build_public_form(child)
    form_inst = FormClass(request.POST, request.FILES)
    if not form_inst.is_valid():
        return (
            {
                "ok": False,
                "error": "validation_failed",
                "message": "Please fix the highlighted fields.",
                "field_errors": _field_errors_from_form(form_inst),
            },
            400,
        )

    from magicforms.submit_validation import check_pre_submit_validation

    force_submit = (request.POST.get("validation_force_submit") or "").strip() == "1"
    api_validation = check_pre_submit_validation(
        child,
        form_inst.cleaned_data,
        FormClass._magicforms_fields_def,
        request,
        force_submit=force_submit,
    )
    if not api_validation.proceed:
        return (
            {
                "ok": False,
                "error": "api_validation_failed",
                "message": api_validation.message,
                "status_code": api_validation.status_code,
                "can_force_submit": api_validation.can_force_submit,
                "api_unreachable": api_validation.api_unreachable,
            },
            400,
        )

    initial_step = child.initial_workflow_step()
    submitter_email = (parent.submitter_email or "").strip()
    if not submitter_email and parent.submitted_by_id:
        submitter_email = (getattr(parent.submitted_by, "email", None) or "").strip()
    sub = FormSubmission.objects.create(
        form=child,
        submitter_email=submitter_email,
        current_step=initial_step,
        submitted_by=parent.submitted_by,
    )
    row.child_submission = sub
    row.save(update_fields=["child_submission"])

    from magicforms.dynamic_forms import field_collects_answer, serialize_value

    for ff in FormClass._magicforms_fields_def:
        if not field_collects_answer(ff):
            continue
        key = f"f_{ff.pk}"
        raw = form_inst.cleaned_data.get(key)
        if ff.field_type == FieldType.FILE:
            defaults = {"value": "", "attachment": None}
            if raw:
                defaults["value"] = getattr(raw, "name", "") or ""
                defaults["attachment"] = raw
            sub.values.update_or_create(field=ff, defaults=defaults)
        else:
            sub.values.update_or_create(
                field=ff,
                defaults={"value": serialize_value(ff, raw), "attachment": None},
            )
    submit_event = SubmissionEvent.objects.create(
        submission=sub,
        kind=SubmissionEvent.Kind.SUBMITTED,
        step=initial_step,
        message="Form submitted.",
    )
    from magicforms.workflow_decision import apply_submit_route_role

    apply_submit_route_role(sub)
    queue_after_submission_event(sub, submit_event, request=request)
    record_related_child_submitted(parent, child.title)

    from magicforms.subdomain import portal_absolute_uri

    detail_url = portal_absolute_uri(
        request,
        "magicforms:submission_detail",
        entity=child.entity,
        slug=child.slug,
        token=sub.reference_token,
    )
    return (
        {
            "ok": True,
            "submission": {
                "id": sub.pk,
                "reference_token": sub.reference_token or "",
                "detail_url": detail_url,
            },
        },
        200,
    )
