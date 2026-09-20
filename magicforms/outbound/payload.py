"""Build JSON payloads from form outbound field maps."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from magicforms.models import FieldType, FormField, FormOutboundFieldMap, FormSubmission, SubmissionEvent, SubmissionValue

from .applicant_data import resolve_applicant_value
from .file_urls import absolute_outbound_file_url, outbound_file_url_max_age


SYSTEM_SOURCES = {
    "submission.reference_token",
    "submission.submitted_at",
    "submission.submitter_email",
    "submission.workflow_state",
    "submission.current_step_label",
    "form.slug",
    "form.title",
    "entity.slug",
    "entity.name",
    "event.kind",
    "event.message",
    "event.created_at",
    "event.actor_username",
    "workflow.decision",
    "workflow.decision_comment",
    "workflow.state",
    "workflow.step_label",
    "trigger",
}


def _iso_datetime(dt) -> str:
    if dt is None:
        return ""
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _transform_scalar(raw: str, transform: str) -> Any:
    if transform == FormOutboundFieldMap.Transform.ISO_DATE:
        return raw
    if transform == FormOutboundFieldMap.Transform.BOOL_YES_NO:
        return "yes" if (raw or "").lower() in ("yes", "true", "1", "on") else "no"
    if transform == FormOutboundFieldMap.Transform.JSON_ARRAY:
        parts = [p.strip() for p in (raw or "").split("\n") if p.strip()]
        return parts
    return raw


def _submission_values_by_field_name(submission: FormSubmission) -> dict[str, SubmissionValue]:
    return {sv.field.name: sv for sv in submission.values.select_related("field").all()}


def _file_field_payload(
    sv: SubmissionValue,
    transform: str,
    *,
    request=None,
) -> Any:
    if not sv.attachment:
        return ""
    filename = (sv.value or "").strip()
    if not filename:
        filename = sv.attachment.name.split("/")[-1]
    signed_url = absolute_outbound_file_url(sv.pk, request=request)
    max_age = outbound_file_url_max_age()
    if transform in (
        FormOutboundFieldMap.Transform.FILE_SIGNED_URL,
        "file_signed_url",
    ):
        return signed_url
    if transform in (
        FormOutboundFieldMap.Transform.FILE_FILENAME,
        "file_filename",
    ):
        return filename
    return {
        "filename": filename,
        "signed_url": signed_url,
        "expires_in_seconds": max_age,
    }


def _form_field_value(
    field: FormField,
    sv: SubmissionValue | None,
    transform: str,
    *,
    request=None,
) -> Any:
    if sv is None:
        return ""
    if field.field_type == FieldType.FILE:
        effective = transform
        if effective in (FormOutboundFieldMap.Transform.NONE, "", None):
            effective = FormOutboundFieldMap.Transform.FILE_DETAILS
        return _file_field_payload(sv, effective, request=request)
    return _transform_scalar((sv.value or "").strip(), transform)


def _system_value(
    key: str,
    submission: FormSubmission,
    *,
    trigger: str,
    event: SubmissionEvent | None,
    workflow_decision: str,
    workflow_decision_comment: str,
) -> Any:
    form = submission.form
    entity = form.entity
    if key == "submission.reference_token":
        return submission.reference_token
    if key == "submission.submitted_at":
        return _iso_datetime(submission.submitted_at)
    if key == "submission.submitter_email":
        return submission.submitter_email or ""
    if key == "submission.workflow_state":
        return submission.workflow_state
    if key == "submission.current_step_label":
        return submission.get_print_current_step_label()
    if key == "form.slug":
        return form.slug
    if key == "form.title":
        return form.title
    if key == "entity.slug":
        return entity.slug
    if key == "entity.name":
        return entity.name
    if key == "trigger":
        return trigger
    if key == "workflow.decision":
        return workflow_decision or ""
    if key == "workflow.decision_comment":
        return workflow_decision_comment or ""
    if key == "workflow.state":
        return submission.workflow_state
    if key == "workflow.step_label":
        if submission.current_step_id and submission.current_step:
            return submission.current_step.label
        if event and event.step_id and event.step:
            return event.step.label
        return ""
    if key == "event.kind":
        return event.kind if event else ""
    if key == "event.message":
        return (event.message or "") if event else ""
    if key == "event.created_at":
        return _iso_datetime(event.created_at) if event else ""
    if key == "event.actor_username":
        if event and event.created_by_id:
            return getattr(event.created_by, "username", "") or ""
        return ""
    return ""


def _value_is_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    if isinstance(val, dict):
        return not (val.get("signed_url") or val.get("filename"))
    return False


def build_outbound_payload(
    config,
    submission: FormSubmission,
    *,
    trigger: str,
    event: SubmissionEvent | None = None,
    workflow_decision: str = "",
    workflow_decision_comment: str = "",
    request=None,
) -> dict[str, Any]:
    values_by_name = _submission_values_by_field_name(submission)
    fields_by_name = {ff.name: ff for ff in submission.form.fields.all()}
    body: dict[str, Any] = {}
    maps = list(config.field_maps.order_by("order", "id"))
    for row in maps:
        val: Any = ""
        if row.source_type == FormOutboundFieldMap.SourceType.FORM_FIELD:
            ref = (row.source_ref or "").strip()
            ff = fields_by_name.get(ref)
            sv = values_by_name.get(ref)
            if ff is not None:
                val = _form_field_value(ff, sv, row.transform, request=request)
            else:
                val = ""
        elif row.source_type == FormOutboundFieldMap.SourceType.APPLICANT:
            val = resolve_applicant_value(submission, (row.source_ref or "").strip())
        elif row.source_type == FormOutboundFieldMap.SourceType.CONSTANT:
            val = row.source_ref or ""
        elif row.source_type == FormOutboundFieldMap.SourceType.SYSTEM:
            val = _system_value(
                (row.source_ref or "").strip(),
                submission,
                trigger=trigger,
                event=event,
                workflow_decision=workflow_decision,
                workflow_decision_comment=workflow_decision_comment,
            )
        if isinstance(val, str):
            if row.required and not val.strip():
                raise ValueError(f"Required outbound field “{row.external_key}” has no value.")
            if not val.strip() and not row.required:
                continue
            body[row.external_key] = _transform_scalar(val, row.transform)
        else:
            if row.required and _value_is_empty(val):
                raise ValueError(f"Required outbound field “{row.external_key}” has no value.")
            if _value_is_empty(val) and not row.required:
                continue
            body[row.external_key] = val

    root = (config.payload_root_key or "").strip()
    if root:
        return {root: body}
    return body
