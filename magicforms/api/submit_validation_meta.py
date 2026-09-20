"""Mobile API metadata for pre-submit validation."""

from __future__ import annotations

from magicforms.models import Form, FormSubmitValidationConfig
from magicforms.submit_validation.runner import _config_ready, get_submit_validation_config


def submit_validation_meta_for_form(form: Form) -> dict:
    config = get_submit_validation_config(form)
    active = bool(config and _config_ready(config))
    can_force = bool(
        active
        and config
        and config.failure_action == FormSubmitValidationConfig.FailureAction.ALLOW_CONTINUE
    )
    return {"active": active, "can_force_submit": can_force}
