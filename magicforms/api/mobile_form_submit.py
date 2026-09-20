"""Mobile API: load published form schema and submit responses."""

from __future__ import annotations

from types import SimpleNamespace

from django.db import transaction
from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404
from django.utils.dateformat import format as date_format

from magicforms.api.mobile_content import serialize_published_form
from magicforms.dynamic_forms import (
    build_public_form,
    build_visibility_rules,
    field_collects_answer,
    serialize_value,
)
from magicforms.entity_access import published_forms_for_public_home
from magicforms.field_validation import text_max_length_for_field, textarea_max_length_for_field
from magicforms.i18n_db import gettext_db
from magicforms.models import FieldType, Form, FormSubmission, SubmissionEvent
from magicforms.notification_emails import queue_after_submission_event
from magicforms.subdomain import portal_absolute_uri
from magicforms.supplementary import ensure_related_invitations
from magicforms.user_mapping import build_initial_from_mappings


def _mobile_user(request: HttpRequest):
    return getattr(request, "mobile_user", None)


def _request_for_mapping(user):
    return SimpleNamespace(user=user, session={})


def _get_form_for_mobile(request: HttpRequest, form_id: int) -> Form:
    user = _mobile_user(request)
    allowed = published_forms_for_public_home(user).filter(pk=form_id)
    if not allowed.exists():
        raise Http404
    return get_object_or_404(
        Form.objects.select_related("category", "entity", "submit_validation_config")
        .prefetch_related("sections", "fields__visibility_control_field"),
        pk=form_id,
        deleted_at__isnull=True,
    )


def _form_submit_status(form: Form, user) -> str:
    if not form.is_published:
        return "unpublished"
    if form.submission_deadline_has_passed():
        return "closed"
    if not form.get_ordered_fields().exists():
        return "no_fields"
    if form.one_time_submit and FormSubmission.objects.filter(
        form=form, submitted_by=user
    ).exists():
        return "already_submitted"
    return "open"


def _serialize_initial_value(ff, value) -> str | list[str] | bool | None:
    if value is None:
        return None
    if ff.field_type == FieldType.CHECKBOX:
        return bool(value)
    if ff.field_type == FieldType.CHECKLIST:
        if isinstance(value, (list, tuple)):
            return [str(x).strip() for x in value if str(x).strip()]
        if isinstance(value, str) and value.strip():
            return [p for p in value.split("\n") if p.strip()]
        return []
    if ff.field_type == FieldType.DATE:
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    return str(value)


def _serialize_field(ff) -> dict:
    payload = {
        "id": ff.pk,
        "key": f"f_{ff.pk}",
        "name": ff.name,
        "field_type": ff.field_type,
        "label": gettext_db(ff.label),
        "hint": gettext_db(ff.hint) if ff.hint else "",
        "help_text": gettext_db(ff.help_text) if ff.help_text else "",
        "placeholder": gettext_db(ff.placeholder) if ff.placeholder else "",
        "required": ff.required,
        "choices": ff.choice_list(),
        "options_layout": ff.options_layout,
        "inline": ff.inline,
        "section_id": ff.section_id,
        "visibility_control_field_id": ff.visibility_control_field_id,
        "visibility_values": ff.visibility_trigger_values(),
    }
    if ff.field_type in (FieldType.TEXT, FieldType.EMAIL, FieldType.SELECT, FieldType.RADIO):
        payload["max_length"] = text_max_length_for_field(ff)
    elif ff.field_type == FieldType.TEXTAREA:
        payload["max_length"] = textarea_max_length_for_field(ff)
    return payload


def form_schema_payload(request: HttpRequest, form_id: int) -> dict:
    form = _get_form_for_mobile(request, form_id)
    user = _mobile_user(request)
    status = _form_submit_status(form, user)
    fields_def = list(form.get_ordered_fields())
    sections = [
        {
            "id": s.pk,
            "title": gettext_db(s.title),
            "description": gettext_db(s.description) if s.description else "",
            "starts_collapsed": s.starts_collapsed,
            "order": s.order,
        }
        for s in form.get_ordered_sections()
    ]
    initial_raw = build_initial_from_mappings(_request_for_mapping(user), fields_def)
    initial = {
        key: _serialize_initial_value(
            next(ff for ff in fields_def if f"f_{ff.pk}" == key),
            val,
        )
        for key, val in initial_raw.items()
    }
    from magicforms.api.submit_validation_meta import submit_validation_meta_for_form

    return {
        "form": serialize_published_form(request, form),
        "status": status,
        "status_message": _status_message(status, form),
        "sections": sections,
        "fields": [_serialize_field(ff) for ff in fields_def],
        "initial": initial,
        "visibility_rules": build_visibility_rules(fields_def),
        "submit_validation": submit_validation_meta_for_form(form),
    }


def _status_message(status: str, form: Form) -> str:
    if status == "closed":
        deadline = form.submission_deadline
        label = date_format(deadline, "M j, Y") if deadline else ""
        if label:
            return f"This form closed on {label}."
        return "This form is no longer accepting responses."
    if status == "already_submitted":
        return "You have already submitted this form."
    if status == "no_fields":
        return "This form has no fields yet."
    if status == "unpublished":
        return "This form is not published."
    return ""


def _field_errors_from_form(django_form) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, errs in django_form.errors.items():
        if key == "__all__":
            continue
        out[key] = [str(e) for e in errs]
    return out


def _create_submission_from_valid_form(request: HttpRequest, form_def: Form, FormClass, form_inst):
    user = _mobile_user(request)
    initial_step = form_def.initial_workflow_step()
    submitter_email = (getattr(user, "email", None) or "").strip()
    sub = FormSubmission.objects.create(
        form=form_def,
        submitter_email=submitter_email,
        current_step=initial_step,
        submitted_by=user,
    )
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
                defaults={
                    "value": serialize_value(ff, raw),
                    "attachment": None,
                },
            )
    submit_event = SubmissionEvent.objects.create(
        submission=sub,
        kind=SubmissionEvent.Kind.SUBMITTED,
        step=initial_step,
        message="Form submitted.",
    )
    ensure_related_invitations(sub)
    queue_after_submission_event(sub, submit_event, request=request)
    return sub


def form_submit_payload(request: HttpRequest, form_id: int) -> tuple[dict, int]:
    form = _get_form_for_mobile(request, form_id)
    user = _mobile_user(request)
    status = _form_submit_status(form, user)
    if status != "open":
        return (
            {
                "ok": False,
                "error": "form_not_accepting",
                "message": _status_message(status, form) or "This form cannot be submitted.",
                "status": status,
            },
            400,
        )

    FormClass = build_public_form(form)
    form_inst = FormClass(request.POST, request.FILES)
    if not form_inst.is_valid():
        field_errors = _field_errors_from_form(form_inst)
        non_field = [str(e) for e in form_inst.non_field_errors()]
        message = non_field[0] if non_field else "Please fix the highlighted fields."
        return (
            {
                "ok": False,
                "error": "validation_failed",
                "message": message,
                "field_errors": field_errors,
            },
            400,
        )

    from magicforms.submit_validation import check_pre_submit_validation

    force_submit = (request.POST.get("validation_force_submit") or "").strip() == "1"
    api_validation = check_pre_submit_validation(
        form,
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

    sub = _create_submission_from_valid_form(request, form, FormClass, form_inst)
    detail_url = portal_absolute_uri(
        request,
        "magicforms:submission_detail",
        entity=form.entity,
        slug=form.slug,
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
