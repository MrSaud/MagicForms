"""Per-user to-do items linked to form submissions (studio inbox & detail)."""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.db.models import F, QuerySet
from django.utils import timezone

from .models import FormSubmission, UserSubmissionTask

TASK_DUE_SOON_DAYS = 5
from .workflow_access import submission_in_portal_search_scope


def user_may_task_submission(user, submission: FormSubmission, request) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if submission.form.deleted_at is not None:
        return False
    return submission_in_portal_search_scope(user, submission, request)


def user_task_submission_ids(user, *, include_done: bool = True) -> set[int]:
    qs = UserSubmissionTask.objects.filter(user=user)
    if not include_done:
        qs = qs.filter(is_done=False)
    return set(qs.values_list("submission_id", flat=True))


def task_due_urgency(
    due_date: dt.date | None,
    *,
    reference_date: dt.date | None = None,
) -> str:
    """
    Return ``''``, ``'due_soon'`` (due within TASK_DUE_SOON_DAYS days), or ``'overdue'``.
    """
    if due_date is None:
        return ""
    today = reference_date or timezone.localdate()
    if due_date < today:
        return "overdue"
    if due_date <= today + dt.timedelta(days=TASK_DUE_SOON_DAYS):
        return "due_soon"
    return ""


def tasks_for_user(user, *, include_done: bool = False) -> QuerySet:
    qs = (
        UserSubmissionTask.objects.filter(user=user)
        .select_related(
            "submission",
            "submission__form",
            "submission__form__entity",
            "submission__current_step",
        )
        .order_by("-is_done", F("due_date").asc(nulls_last=True), "-created_at")
    )
    if not include_done:
        qs = qs.filter(is_done=False)
    return qs


def open_task_count_for_user(user) -> int:
    if not getattr(user, "is_authenticated", False):
        return 0
    return UserSubmissionTask.objects.filter(user=user, is_done=False).count()


def add_submission_task(
    user,
    submission: FormSubmission,
    *,
    note: str = "",
    due_date: dt.date | None = None,
) -> tuple[bool, str]:
    """Returns (created, message_key)."""
    note = (note or "").strip()[: UserSubmissionTask.MAX_NOTE_LEN]
    _obj, created = UserSubmissionTask.objects.get_or_create(
        user=user,
        submission=submission,
        defaults={"note": note, "due_date": due_date},
    )
    if not created and due_date is not None and _obj.due_date != due_date:
        _obj.due_date = due_date
        _obj.save(update_fields=["due_date", "updated_at"])
    return created, "added" if created else "already"


def set_submission_task_due_date(
    user,
    submission: FormSubmission,
    due_date: dt.date | None,
) -> bool:
    """Set or clear deadline. Returns False if the user has no task row."""
    row = UserSubmissionTask.objects.filter(user=user, submission=submission).first()
    if not row:
        return False
    row.due_date = due_date
    row.save(update_fields=["due_date", "updated_at"])
    return True


def remove_submission_task(user, submission: FormSubmission) -> bool:
    n, _ = UserSubmissionTask.objects.filter(user=user, submission=submission).delete()
    return n > 0


def toggle_submission_task_done(user, submission: FormSubmission) -> bool | None:
    """Toggle is_done; return new value or None if no task row."""
    row = UserSubmissionTask.objects.filter(user=user, submission=submission).first()
    if not row:
        return None
    row.is_done = not row.is_done
    row.save(update_fields=["is_done", "updated_at"])
    return row.is_done
