"""Call the configured validation API before persisting a submission."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from magicforms.models import Form, FormOutboundConfig, FormSubmitValidationConfig
from magicforms.outbound.http_client import send_json_integration_post

from .messages import applicant_validation_message, extract_api_message
from .payload import build_pre_submit_validation_payload, wrap_validation_payload

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreSubmitValidationResult:
    proceed: bool
    message: str = ""
    status_code: int | None = None
    can_force_submit: bool = False
    api_unreachable: bool = False


def get_submit_validation_config(form_def: Form) -> FormSubmitValidationConfig | None:
    try:
        return form_def.submit_validation_config
    except FormSubmitValidationConfig.DoesNotExist:
        return None


def _config_ready(config: FormSubmitValidationConfig | None) -> bool:
    if config is None:
        return False
    if not config.is_active:
        return False
    if not (config.endpoint_url or "").strip():
        return False
    if config.auth_type != FormOutboundConfig.AuthType.NONE and not config.has_secret():
        return False
    return True


def check_pre_submit_validation(
    form_def: Form,
    cleaned_data: dict,
    fields_def,
    request,
    *,
    force_submit: bool = False,
) -> PreSubmitValidationResult:
    """
    When active, POST answers to the validation API. HTTP 2xx allows submit.
    """
    config = get_submit_validation_config(form_def)
    if not _config_ready(config):
        return PreSubmitValidationResult(proceed=True)

    assert config is not None
    if force_submit and config.failure_action == FormSubmitValidationConfig.FailureAction.ALLOW_CONTINUE:
        return PreSubmitValidationResult(proceed=True)

    body = build_pre_submit_validation_payload(
        form_def,
        cleaned_data,
        fields_def,
        request=request,
    )
    payload = wrap_validation_payload(config, body)
    url = (config.endpoint_url or "").strip()

    try:
        status, raw_body, _redacted, _sent = send_json_integration_post(
            config,
            url=url,
            payload=payload,
            extra_headers={
                "X-MagicForms-Validation": "1",
                "X-MagicForms-Form-Id": str(form_def.pk),
            },
            idempotency_key=str(uuid.uuid4()),
        )
    except ConnectionError as exc:
        logger.warning("Pre-submit validation unreachable form=%s: %s", form_def.pk, exc)
        msg = applicant_validation_message(config, "unreachable")
        if config.failure_action == FormSubmitValidationConfig.FailureAction.ALLOW_CONTINUE:
            return PreSubmitValidationResult(
                proceed=False,
                message=msg,
                api_unreachable=True,
                can_force_submit=True,
            )
        return PreSubmitValidationResult(
            proceed=False,
            message=msg,
            api_unreachable=True,
        )
    except Exception:
        logger.exception("Pre-submit validation failed form=%s", form_def.pk)
        msg = applicant_validation_message(config, "error")
        if config.failure_action == FormSubmitValidationConfig.FailureAction.ALLOW_CONTINUE:
            return PreSubmitValidationResult(
                proceed=False,
                message=msg,
                api_unreachable=True,
                can_force_submit=True,
            )
        return PreSubmitValidationResult(proceed=False, message=msg, api_unreachable=True)

    if 200 <= status < 300:
        return PreSubmitValidationResult(proceed=True, status_code=status)

    msg = applicant_validation_message(
        config,
        "rejected",
        status=status,
        api_message=extract_api_message(raw_body),
    )
    if config.failure_action == FormSubmitValidationConfig.FailureAction.ALLOW_CONTINUE:
        return PreSubmitValidationResult(
            proceed=False,
            message=msg,
            status_code=status,
            can_force_submit=True,
        )
    return PreSubmitValidationResult(
        proceed=False,
        message=msg,
        status_code=status,
    )
