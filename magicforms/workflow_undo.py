"""Time-limited undo for the last approve / complete action (same actor, timeline-audited)."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Form, FormSubmission, SubmissionEvent
from .supplementary import ensure_related_invitations
from .workflow_access import delegate_action_suffix

UNDO_APPROVE_WINDOW = timedelta(minutes=5)
UNDO_APPROVE_MINUTES = int(UNDO_APPROVE_WINDOW.total_seconds() // 60)

# Timeline kinds that define the “workflow tail” for undo eligibility.
WORKFLOW_TAIL_EVENT_KINDS = frozenset(
    {
        SubmissionEvent.Kind.STEP_APPROVED,
        SubmissionEvent.Kind.WORKFLOW_COMPLETED,
        SubmissionEvent.Kind.WORKFLOW_REJECTED,
        SubmissionEvent.Kind.STEP_CHANGED,
        SubmissionEvent.Kind.APPROVE_UNDONE,
    }
)


def last_undoable_approve_event(user, submission: FormSubmission) -> SubmissionEvent | None:
    """
    The most recent tail event on this submission, if it is a STEP_APPROVED or
    WORKFLOW_COMPLETED authored by ``user`` within :data:`UNDO_APPROVE_WINDOW`,
    submission state still matches that action, and no blocking workflow tail
    appeared after it.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    last_tail = (
        SubmissionEvent.objects.filter(submission_id=submission.pk, kind__in=WORKFLOW_TAIL_EVENT_KINDS)
        .order_by("-created_at", "-id")
        .select_related("step", "created_by")
        .first()
    )
    if last_tail is None:
        return None
    if last_tail.kind not in (
        SubmissionEvent.Kind.STEP_APPROVED,
        SubmissionEvent.Kind.WORKFLOW_COMPLETED,
    ):
        return None
    if last_tail.created_by_id != user.pk:
        return None
    if timezone.now() - last_tail.created_at > UNDO_APPROVE_WINDOW:
        return None

    if last_tail.kind == SubmissionEvent.Kind.STEP_APPROVED:
        if submission.workflow_state != FormSubmission.WorkflowState.IN_PROGRESS:
            return None
        if submission.current_step_id != last_tail.step_id:
            return None
    else:
        if submission.workflow_state != FormSubmission.WorkflowState.COMPLETED:
            return None
        if submission.current_step_id is not None:
            return None

    return last_tail


def perform_undo_last_approve(*, user, form_instance: Form, submission_id: int) -> tuple[bool, str]:
    """
    Revert the last approve/complete (see :func:`last_undoable_approve_event`), append
    :data:`SubmissionEvent.Kind.APPROVE_UNDONE` to the timeline, and refresh related invitations.

    Returns ``(True, "")`` on success, or ``(False, translated_error_message)``.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False, _("You must be signed in.")

    try:
        with transaction.atomic():
            fresh = (
                FormSubmission.objects.select_for_update()
                .select_related("current_step")
                .prefetch_related("current_step__assigned_users")
                .get(pk=submission_id, form=form_instance)
            )
            last_tail = last_undoable_approve_event(user, fresh)
            if last_tail is None:
                return False, _("This approval can no longer be undone (deadline passed or submission changed).")

            delegate_suffix = delegate_action_suffix(user, fresh)

            if last_tail.kind == SubmissionEvent.Kind.WORKFLOW_COMPLETED:
                last_step = form_instance.workflow_steps.order_by("order", "id").last()
                if last_step is None:
                    return False, _("This form has no workflow steps.")
                fresh.workflow_state = FormSubmission.WorkflowState.IN_PROGRESS
                fresh.current_step = last_step
                fresh.save(update_fields=["workflow_state", "current_step", "updated_at"])
            else:
                assert last_tail.step_id is not None
                prev_step = form_instance.previous_workflow_step_before(last_tail.step)
                if prev_step is None:
                    return False, _("Cannot undo this approval (missing previous step).")
                fresh.workflow_state = FormSubmission.WorkflowState.IN_PROGRESS
                fresh.current_step = prev_step
                fresh.save(update_fields=["workflow_state", "current_step", "updated_at"])

            mins = int(UNDO_APPROVE_WINDOW.total_seconds() // 60)
            msg = (
                _("Approval undone (within %(minutes)d minutes). Workflow position reverted.") % {"minutes": mins}
            )[:1000]
            if delegate_suffix:
                msg = (msg + delegate_suffix)[:1000]
            SubmissionEvent.objects.create(
                submission=fresh,
                kind=SubmissionEvent.Kind.APPROVE_UNDONE,
                step=fresh.current_step if fresh.current_step_id else None,
                message=msg,
                created_by=user,
            )
            ensure_related_invitations(fresh)
    except FormSubmission.DoesNotExist:
        return False, _("Submission not found.")

    return True, ""
