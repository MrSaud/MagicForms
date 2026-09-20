"""Applicant-facing messages for pre-submit validation failures."""

from __future__ import annotations

import json
import re
from typing import Any

from django.utils.translation import gettext as _

from magicforms.models import FormSubmitValidationConfig

_APPLICANT_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

DEFAULT_REJECTED = _(
    "The validation service did not accept your answers (HTTP %(status)s)."
)
DEFAULT_UNREACHABLE = _("Could not reach the validation service. Please try again later.")
DEFAULT_ERROR = _("Validation service error. Please try again later.")

APPLICANT_MESSAGE_PLACEHOLDERS = "{{status}}, {{api_message}}"


def render_applicant_message(template: str, context: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        return context.get(match.group(1), "")

    return _APPLICANT_PLACEHOLDER_RE.sub(repl, template or "").strip()


def extract_api_message(raw_body: str) -> str:
    """Best-effort message from validation API JSON or plain text."""
    text = (raw_body or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text[: FormSubmitValidationConfig.MAX_APPLICANT_MESSAGE_LEN]
    if isinstance(data, str):
        return data.strip()[: FormSubmitValidationConfig.MAX_APPLICANT_MESSAGE_LEN]
    if not isinstance(data, dict):
        return ""
    for key in ("message", "detail", "error", "reason", "description"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[: FormSubmitValidationConfig.MAX_APPLICANT_MESSAGE_LEN]
        if isinstance(val, list) and val:
            first = val[0]
            if isinstance(first, str) and first.strip():
                return first.strip()[: FormSubmitValidationConfig.MAX_APPLICANT_MESSAGE_LEN]
            if isinstance(first, dict):
                nested = first.get("message") or first.get("detail")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()[: FormSubmitValidationConfig.MAX_APPLICANT_MESSAGE_LEN]
    return ""


def applicant_validation_message(
    config: FormSubmitValidationConfig,
    kind: str,
    *,
    status: int | None = None,
    api_message: str = "",
) -> str:
    """
    ``kind`` is ``rejected``, ``unreachable``, or ``error``.
    """
    field_map = {
        "rejected": "message_rejected",
        "unreachable": "message_unreachable",
        "error": "message_error",
    }
    defaults = {
        "rejected": DEFAULT_REJECTED,
        "unreachable": DEFAULT_UNREACHABLE,
        "error": DEFAULT_ERROR,
    }
    field_name = field_map.get(kind)
    if not field_name:
        return ""
    custom = (getattr(config, field_name, None) or "").strip()
    if custom:
        ctx = {
            "status": str(status) if status is not None else "",
            "api_message": (api_message or "").strip(),
        }
        return render_applicant_message(custom, ctx)[
            : FormSubmitValidationConfig.MAX_APPLICANT_MESSAGE_LEN
        ]
    default = defaults[kind]
    if kind == "rejected":
        return str(default % {"status": status if status is not None else "?"})
    return str(default)
