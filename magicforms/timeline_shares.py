"""Share submission timeline access with organization members (staff and non-staff)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from .entity_access import entity_users_for_entity_search
from .models import FormSubmission, SubmissionTimelineShare
from .workflow_access import submission_in_portal_search_scope

User = get_user_model()


def _active_share_filter():
    return {"dismissed_at__isnull": True}


def user_has_timeline_share(user, submission: FormSubmission) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    return SubmissionTimelineShare.objects.filter(
        submission=submission,
        user=user,
        **_active_share_filter(),
    ).exists()


def user_may_view_submission_timeline(user, submission: FormSubmission, request) -> bool:
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    if submission_in_portal_search_scope(user, submission, request):
        return True
    return user_has_timeline_share(user, submission)


def user_may_manage_timeline_sharing(user, submission: FormSubmission, request=None) -> bool:
    """Update who can open the full-page timeline (not share-only viewers)."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    return submission_in_portal_search_scope(user, submission, request)


def timeline_share_for_user(
    user, submission: FormSubmission
) -> SubmissionTimelineShare | None:
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        SubmissionTimelineShare.objects.filter(
            submission=submission,
            user=user,
            **_active_share_filter(),
        )
        .select_related("shared_by")
        .first()
    )


def timeline_share_targets_queryset(actor, submission: FormSubmission, q: str = "") -> QuerySet:
    """Active org members eligible to receive timeline access."""
    return entity_users_for_entity_search(submission.form.entity_id, q=q).exclude(pk=actor.pk)


def timeline_shares_for_submission(submission: FormSubmission) -> QuerySet:
    return (
        SubmissionTimelineShare.objects.filter(submission=submission, **_active_share_filter())
        .select_related("user", "shared_by")
    )


def timeline_share_message_for_submission(submission: FormSubmission) -> str:
    row = (
        timeline_shares_for_submission(submission)
        .exclude(share_message="")
        .order_by("-updated_at")
        .values_list("share_message", flat=True)
        .first()
    )
    return row or ""


def shared_timelines_for_user(user, request=None, *, limit: int = 50) -> list[SubmissionTimelineShare]:
    """
    Timeline pages shared with ``user`` (studio home list).

    Uses organization membership, not superuser session scope — a share is explicit access
    regardless of the Home “organization scope” filter.
    """
    from .models import EntityMembership

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return []
    qs = (
        SubmissionTimelineShare.objects.filter(user=user, **_active_share_filter())
        .select_related(
            "submission",
            "submission__form",
            "submission__form__entity",
            "shared_by",
        )
        .order_by("-created_at")
    )
    if not user.is_superuser:
        member_ids = list(
            EntityMembership.objects.filter(user=user).values_list("entity_id", flat=True)
        )
        if not member_ids:
            return []
        qs = qs.filter(submission__form__entity_id__in=member_ids)
    qs = qs.filter(submission__form__deleted_at__isnull=True)
    return list(qs[:limit])


def record_timeline_share_viewed(user, submission: FormSubmission) -> None:
    """First open of a shared timeline (clears the Home list star)."""
    now = timezone.now()
    SubmissionTimelineShare.objects.filter(
        submission=submission,
        user=user,
        first_viewed_at__isnull=True,
        **_active_share_filter(),
    ).update(first_viewed_at=now, updated_at=now)


def dismiss_timeline_share_for_user(user, submission: FormSubmission) -> bool:
    """Recipient removes this share from Home and loses share-only access."""
    now = timezone.now()
    updated = SubmissionTimelineShare.objects.filter(
        submission=submission,
        user=user,
        dismissed_at__isnull=True,
    ).update(dismissed_at=now, updated_at=now)
    return updated > 0


def parse_share_user_ids_from_post(post) -> list[int]:
    """Tom Select sync field first (reliable), then native ``share_user_ids`` multi-select."""
    sync = (post.get("share_user_ids_sync") or "").strip()
    if "share_user_ids_sync" in post:
        if not sync:
            return []
        return [int(x) for x in sync.split(",") if str(x).strip().isdigit()]
    return [int(x) for x in post.getlist("share_user_ids") if str(x).isdigit()]


@transaction.atomic
def set_submission_timeline_shares(
    actor,
    submission: FormSubmission,
    *,
    user_ids: list[int],
    share_message: str = "",
) -> list[SubmissionTimelineShare]:
    if not user_may_manage_timeline_sharing(actor, submission):
        raise PermissionError
    message = (share_message or "").strip()[: SubmissionTimelineShare.MAX_SHARE_MESSAGE_LEN]
    allowed = set(
        timeline_share_targets_queryset(actor, submission)
        .filter(pk__in=user_ids)
        .values_list("pk", flat=True)
    )
    if not allowed and not user_ids:
        if message:
            SubmissionTimelineShare.objects.filter(
                submission=submission,
                **_active_share_filter(),
            ).update(share_message=message, shared_by=actor)
        return []

    if user_ids and not allowed:
        raise ValueError("no eligible share recipients")

    SubmissionTimelineShare.objects.filter(submission=submission).exclude(user_id__in=allowed).delete()

    created: list[SubmissionTimelineShare] = []
    for uid in allowed:
        row, was_created = SubmissionTimelineShare.objects.update_or_create(
            submission=submission,
            user_id=uid,
            defaults={
                "shared_by": actor,
                "share_message": message,
                "dismissed_at": None,
                "first_viewed_at": None,
            },
        )
        if was_created:
            created.append(row)
    return created
