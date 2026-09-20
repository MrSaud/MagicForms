"""JSON body sent to the pre-submit validation endpoint."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from magicforms.dynamic_forms import field_collects_answer
from magicforms.models import FieldType, Form, FormField


def _field_value_for_validation(ff: FormField, raw: Any) -> Any:
    if raw is None:
        return ""
    if ff.field_type == FieldType.FILE:
        return getattr(raw, "name", "") or ""
    if ff.field_type == FieldType.CHECKLIST:
        if isinstance(raw, (list, tuple)):
            return [str(x).strip() for x in raw if str(x).strip()]
        return serialize_value(ff, raw)
    if ff.field_type == FieldType.CHECKBOX:
        return bool(raw)
    return serialize_value(ff, raw)


def build_pre_submit_validation_payload(
    form_def: Form,
    cleaned_data: dict,
    fields_def: list[FormField],
    *,
    request=None,
) -> dict[str, Any]:
    submitter_email = ""
    if request is not None and getattr(request, "user", None) and request.user.is_authenticated:
        submitter_email = (getattr(request.user, "email", None) or "").strip()

    fields: dict[str, Any] = {}
    for ff in fields_def:
        if not field_collects_answer(ff):
            continue
        key = f"f_{ff.pk}"
        fields[ff.name] = _field_value_for_validation(ff, cleaned_data.get(key))

    return {
        "phase": "pre_submit",
        "validated_at": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "form": {
            "id": form_def.pk,
            "slug": form_def.slug,
            "title": form_def.title,
        },
        "entity": {
            "id": form_def.entity_id,
            "slug": form_def.entity.slug,
            "name": form_def.entity.name,
        },
        "submitter_email": submitter_email,
        "fields": fields,
    }


def wrap_validation_payload(config, body: dict[str, Any]) -> dict[str, Any]:
    root = (getattr(config, "payload_root_key", None) or "").strip()
    if root:
        return {root: body}
    return body
