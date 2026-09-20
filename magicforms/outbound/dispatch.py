"""Queue outbound deliveries after submit / workflow actions."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from magicforms.models import FormOutboundConfig, FormOutboundDelivery, FormSubmission, SubmissionEvent

logger = logging.getLogger(__name__)

TRIGGER_SUBMITTED = "submitted"
TRIGGER_STEP_APPROVED = "step_approved"
TRIGGER_WORKFLOW_COMPLETED = "workflow_completed"
TRIGGER_WORKFLOW_REJECTED = "workflow_rejected"

EVENT_KIND_TO_TRIGGER = {
    SubmissionEvent.Kind.SUBMITTED: TRIGGER_SUBMITTED,
    SubmissionEvent.Kind.STEP_APPROVED: TRIGGER_STEP_APPROVED,
    SubmissionEvent.Kind.WORKFLOW_COMPLETED: TRIGGER_WORKFLOW_COMPLETED,
    SubmissionEvent.Kind.WORKFLOW_REJECTED: TRIGGER_WORKFLOW_REJECTED,
}


def _config_wants_trigger(config: FormOutboundConfig, trigger: str) -> bool:
    if trigger == TRIGGER_SUBMITTED:
        return config.trigger_submitted
    if trigger == TRIGGER_STEP_APPROVED:
        return config.trigger_step_approved
    if trigger == TRIGGER_WORKFLOW_COMPLETED:
        return config.trigger_workflow_completed
    if trigger == TRIGGER_WORKFLOW_REJECTED:
        return config.trigger_workflow_rejected
    return False


def dispatch_outbound(
    trigger: str,
    submission: FormSubmission,
    *,
    event: SubmissionEvent | None = None,
    workflow_decision: str = "",
    workflow_decision_comment: str = "",
) -> None:
    """
    Create a pending delivery row when the form has an active outbound config for this trigger.
    Processing happens via ``process_outbound_deliveries`` (cron / management command).
    """
    form_id = submission.form_id
    try:
        config = FormOutboundConfig.objects.get(form_id=form_id)
    except FormOutboundConfig.DoesNotExist:
        return
    if not config.is_active or not (config.endpoint_url or "").strip():
        return
    if not _config_wants_trigger(config, trigger):
        return

    def _create():
        existing = FormOutboundDelivery.objects.filter(
            config=config,
            submission=submission,
            trigger=trigger,
            submission_event=event,
        ).exclude(status=FormOutboundDelivery.Status.DEAD).exists()
        if existing:
            return
        FormOutboundDelivery.objects.create(
            config=config,
            submission=submission,
            trigger=trigger,
            submission_event=event,
            idempotency_key=str(uuid.uuid4()),
            workflow_decision=(workflow_decision or "")[:32],
            workflow_decision_comment=(workflow_decision_comment or "")[:800],
            status=FormOutboundDelivery.Status.PENDING,
            next_retry_at=timezone.now(),
        )
        if getattr(settings, "OUTBOUND_PROCESS_INLINE", False):
            from .worker import process_pending_deliveries

            process_pending_deliveries(limit=1)

    transaction.on_commit(_create)


def dispatch_outbound_for_event(
    submission: FormSubmission,
    event: SubmissionEvent,
    *,
    workflow_decision: str = "",
    workflow_decision_comment: str = "",
) -> None:
    trigger = EVENT_KIND_TO_TRIGGER.get(event.kind)
    if not trigger:
        return
    dispatch_outbound(
        trigger,
        submission,
        event=event,
        workflow_decision=workflow_decision,
        workflow_decision_comment=workflow_decision_comment,
    )
