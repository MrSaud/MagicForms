"""Related (child) form invitations tied to a base workflow submission."""

from __future__ import annotations

import uuid

from django.utils.translation import gettext as _

from .models import SubmissionEvent, SupplementaryFormLink, SupplementarySubmission


def ensure_related_invitations(parent_submission) -> None:
    """
    Create invitation rows when the submission is on a workflow step that triggers a child form.
    Idempotent; emits a timeline event only when a new invitation row is created.

    Runs for any workflow state while ``current_step`` is set (including before an approve
    transitions away from the trigger step). Skips when there is no current step.
    """
    step_id = parent_submission.current_step_id
    if not step_id:
        return
    parent_form_id = parent_submission.form_id
    links = SupplementaryFormLink.objects.filter(
        parent_form_id=parent_form_id,
        trigger_step_id=step_id,
    ).select_related("child_form")
    for link in links:
        cf = link.child_form
        if not cf.is_published or cf.deleted_at is not None:
            continue
        row, created = SupplementarySubmission.objects.get_or_create(
            link=link,
            parent_submission=parent_submission,
            defaults={"access_token": uuid.uuid4()},
        )
        if created:
            SubmissionEvent.objects.create(
                submission=parent_submission,
                kind=SubmissionEvent.Kind.SUPPLEMENTARY_INVITED,
                step=parent_submission.current_step,
                message=(
                    _(
                        'Related form available: "%(title)s". '
                        "Complete it using the link in the related forms section below."
                    )
                    % {"title": link.child_form.title}
                )[:1000],
                created_by=None,
            )


def related_pending_count_for_user(user) -> int:
    """How many related forms this signed-in user still owes (base submission was theirs)."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return 0
    return SupplementarySubmission.objects.filter(
        parent_submission__submitted_by=user,
        child_submission__isnull=True,
        link__child_form__is_published=True,
        link__child_form__deleted_at__isnull=True,
    ).count()


def respondent_may_access_related_form(request, parent_submission) -> bool:
    """
    Only the original applicant may open/submit the child form.
    Anonymous base submissions rely on the secret URL (same as track link semantics).
    Signed-in applicants must match the account used for the base submission.
    """
    uid = parent_submission.submitted_by_id
    if uid:
        return bool(request.user.is_authenticated and request.user.pk == uid)
    return True


def record_related_child_submitted(parent_submission, child_form_title: str) -> None:
    SubmissionEvent.objects.create(
        submission=parent_submission,
        kind=SubmissionEvent.Kind.SUPPLEMENTARY_SUBMITTED,
        step=parent_submission.current_step if parent_submission.current_step_id else None,
        message=(_('Related form submitted: "%(title)s".') % {"title": child_form_title})[:1000],
        created_by=None,
    )
