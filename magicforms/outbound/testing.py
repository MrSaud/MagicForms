"""Studio tests: API health check and sample POST for outbound integration."""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from magicforms.models import FieldType, Form, FormOutboundConfig, FormOutboundFieldMap

from .http_client import redact_headers, send_outbound_post
from .payload import SYSTEM_SOURCES


def config_test_readiness(config: FormOutboundConfig) -> tuple[bool, str]:
    url = (config.endpoint_url or "").strip()
    if not url:
        return False, _("Set the endpoint URL and save the integration first.")
    if config.auth_type != FormOutboundConfig.AuthType.NONE and not config.has_secret():
        return False, _("Set an API secret and save the integration first.")
    return True, ""


def _wrap_payload(config: FormOutboundConfig, body: dict[str, Any]) -> dict[str, Any]:
    root = (config.payload_root_key or "").strip()
    if root:
        return {root: body}
    return body


def _sample_scalar_for_map(row: FormOutboundFieldMap) -> str:
    transform = row.transform
    if transform == FormOutboundFieldMap.Transform.BOOL_YES_NO:
        return "yes"
    if transform == FormOutboundFieldMap.Transform.JSON_ARRAY:
        return "option_a\noption_b"
    if transform == FormOutboundFieldMap.Transform.ISO_DATE:
        return timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    return "sample"


def _sample_file_value(transform: str) -> Any:
    if transform in (
        FormOutboundFieldMap.Transform.FILE_SIGNED_URL,
        "file_signed_url",
    ):
        return "https://example.com/sample-signed-download-url"
    if transform in (
        FormOutboundFieldMap.Transform.FILE_FILENAME,
        "file_filename",
    ):
        return "sample-upload.pdf"
    return {
        "filename": "sample-upload.pdf",
        "signed_url": "https://example.com/sample-signed-download-url",
        "expires_in_seconds": 3600,
    }


def _sample_system_value(key: str) -> Any:
    now = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    samples = {
        "submission.reference_token": "SAMPLE01",
        "submission.submitted_at": now,
        "submission.submitter_email": "applicant@example.com",
        "submission.workflow_state": "in_progress",
        "submission.current_step_label": "Sample step",
        "form.slug": "sample-form",
        "form.title": "Sample form",
        "entity.slug": "sample-org",
        "entity.name": "Sample organization",
        "event.kind": "submitted",
        "event.message": "Sample timeline message",
        "event.created_at": now,
        "event.actor_username": "sample_staff",
        "workflow.decision": "approve",
        "workflow.decision_comment": "Sample approval comment",
        "workflow.state": "in_progress",
        "workflow.step_label": "Sample step",
        "trigger": "test",
    }
    return samples.get(key, f"sample_{key.replace('.', '_')}")


def _sample_applicant_value(key: str) -> str:
    key = (key or "").lower().replace("-", "_")
    samples = {
        "email": "applicant@example.com",
        "username": "sample_applicant",
        "first_name": "Sample",
        "last_name": "Applicant",
        "full_name": "Sample Applicant",
        "employee_number": "EMP-SAMPLE-001",
        "civil_id": "123456789012",
        "job_title": "Sample job title",
        "department": "Sample department",
        "mobile_phone": "+10000000000",
        "manager_username": "sample_manager",
    }
    return samples.get(key, f"sample_{key}")


def build_sample_payload_body(config: FormOutboundConfig, form: Form) -> dict[str, Any]:
    """Synthetic JSON from saved field mappings (no real submission required)."""
    body: dict[str, Any] = {
        "_magicforms": {
            "test": True,
            "kind": "sample_payload",
            "form_id": form.pk,
            "form_slug": form.slug,
        },
    }
    file_field_names = {ff.name for ff in form.fields.all() if ff.field_type == FieldType.FILE}
    for row in config.field_maps.order_by("order", "id"):
        key = row.external_key
        if row.source_type == FormOutboundFieldMap.SourceType.FORM_FIELD:
            ref = (row.source_ref or "").strip()
            if ref in file_field_names:
                body[key] = _sample_file_value(row.transform)
            else:
                body[key] = f"sample_{ref}" if ref else _sample_scalar_for_map(row)
        elif row.source_type == FormOutboundFieldMap.SourceType.APPLICANT:
            body[key] = _sample_applicant_value(row.source_ref)
        elif row.source_type == FormOutboundFieldMap.SourceType.SYSTEM:
            ref = (row.source_ref or "").strip()
            if ref in SYSTEM_SOURCES:
                body[key] = _sample_system_value(ref)
        elif row.source_type == FormOutboundFieldMap.SourceType.CONSTANT:
            body[key] = row.source_ref or "sample"
    if len(body) == 1 and "_magicforms" in body:
        body["sample_note"] = "Add field mappings above, save, then run this test again."
    return body


def build_sample_payload(config: FormOutboundConfig, form: Form) -> dict[str, Any]:
    return _wrap_payload(config, build_sample_payload_body(config, form))


def default_custom_test_json(config: FormOutboundConfig, form: Form) -> str:
    """Default textarea content (before payload root key wrapping)."""
    return json.dumps(build_sample_payload_body(config, form), ensure_ascii=False, indent=2)


def parse_custom_test_payload(config: FormOutboundConfig, raw: str) -> tuple[dict[str, Any] | None, str]:
    text = (raw or "").strip()
    if not text:
        return None, "Enter a JSON object in the body field."
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "JSON body must be an object (e.g. {\"key\": \"value\"})."
    return _wrap_payload(config, data), ""


def format_http_test_error(status: int, response_body: str) -> str:
    """Human-readable test failure including response snippet when available."""
    base = f"HTTP {status}"
    body = (response_body or "").strip()
    if not body:
        return base
    snippet = body.replace("\n", " ")[:280]
    if len(body) > 280:
        snippet += "…"
    return f"{base} — {snippet}"


def build_health_check_payload(form_id: int) -> dict[str, Any]:
    return {
        "_magicforms": {
            "test": True,
            "kind": "health_check",
            "form_id": form_id,
        },
    }


def run_outbound_test(
    config: FormOutboundConfig,
    *,
    form_id: int,
    payload: dict[str, Any],
    trigger: str,
    submission_ref: str,
) -> dict[str, Any]:
    """
    POST to the configured endpoint and return a result dict for the studio UI
    (not queued as a FormOutboundDelivery).
    """
    ok, msg = config_test_readiness(config)
    if not ok:
        return {
            "ok": False,
            "kind": trigger,
            "error": msg,
            "status": None,
            "response": "",
            "request_url": (config.endpoint_url or "").strip(),
            "request_body": "",
            "request_headers": {},
        }
    url = (config.endpoint_url or "").strip()
    event_id = str(uuid.uuid4())
    body_preview = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        status, resp_body, req_headers_redacted, _sent = send_outbound_post(
            config,
            url=url,
            payload=payload,
            idempotency_key=event_id,
            trigger=trigger,
            submission_ref=submission_ref,
            form_id=form_id,
            test_mode=True,
        )
        success = 200 <= status < 300
        return {
            "ok": success,
            "kind": trigger,
            "error": "" if success else format_http_test_error(status, resp_body),
            "status": status,
            "response": resp_body,
            "request_url": url,
            "request_body": body_preview[:12000],
            "request_headers": req_headers_redacted,
            "event_id": event_id,
        }
    except Exception as exc:
        return {
            "ok": False,
            "kind": trigger,
            "error": str(exc),
            "status": None,
            "response": "",
            "request_url": url,
            "request_body": body_preview[:12000],
            "request_headers": redact_headers({}),
            "event_id": event_id,
        }
