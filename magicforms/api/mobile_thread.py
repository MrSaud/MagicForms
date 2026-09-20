"""Mobile API: submission discussion thread."""

from __future__ import annotations

from django.db.models import Max
from django.http import Http404, HttpRequest
from django.utils.dateformat import format as date_format
from django.utils import timezone

from magicforms.api.mobile_content import _get_submission_for_mobile
from magicforms.models import SubmissionThreadLastRead, SubmissionThreadMessage
from magicforms.workflow_access import submission_in_portal_search_scope


def _mobile_user(request: HttpRequest):
    return getattr(request, "mobile_user", None)


def touch_thread_last_read(user, submission) -> None:
    mx = (
        SubmissionThreadMessage.objects.filter(submission_id=submission.pk)
        .aggregate(m=Max("id"))
        .get("m")
        or 0
    )
    SubmissionThreadLastRead.objects.update_or_create(
        user=user,
        submission=submission,
        defaults={"last_seen_message_id": mx},
    )


def _serialize_thread_message(msg: SubmissionThreadMessage) -> dict:
    author = msg.author
    fn = (author.get_full_name() or "").strip()
    return {
        "id": msg.pk,
        "body": msg.body,
        "author_username": author.get_username(),
        "author_display": fn or author.get_username(),
        "created_at": timezone.localtime(msg.created_at).isoformat(),
        "created_at_label": date_format(timezone.localtime(msg.created_at), "M j, Y, P"),
        "is_mine": False,
    }


def thread_messages_payload(request: HttpRequest, submission_id: int) -> dict:
    user = _mobile_user(request)
    submission = _get_submission_for_mobile(request, submission_id)
    touch_thread_last_read(user, submission)
    messages = list(
        SubmissionThreadMessage.objects.filter(submission_id=submission.pk)
        .select_related("author")
        .order_by("created_at", "id")
    )
    items = []
    for msg in messages:
        row = _serialize_thread_message(msg)
        row["is_mine"] = msg.author_id == user.pk
        items.append(row)
    return {
        "messages": items,
        "can_post": submission_in_portal_search_scope(user, submission, request),
        "max_body_length": SubmissionThreadMessage.MAX_BODY_LEN,
    }


def thread_post_payload(request: HttpRequest, submission_id: int, body: str) -> tuple[dict, int]:
    user = _mobile_user(request)
    submission = _get_submission_for_mobile(request, submission_id)
    if not submission_in_portal_search_scope(user, submission, request):
        return (
            {"ok": False, "error": "access_denied", "message": "You cannot post on this thread."},
            403,
        )
    text = (body or "").strip()
    max_len = SubmissionThreadMessage.MAX_BODY_LEN
    if not text:
        return (
            {"ok": False, "error": "validation_failed", "message": "Enter a message before posting."},
            400,
        )
    if len(text) > max_len:
        return (
            {
                "ok": False,
                "error": "validation_failed",
                "message": f"Message is too long ({max_len} characters maximum).",
            },
            400,
        )
    SubmissionThreadMessage.objects.create(
        submission=submission,
        author=user,
        body=text[:max_len],
    )
    touch_thread_last_read(user, submission)
    from magicforms.api.mobile_content import inbox_detail_payload

    return ({"ok": True, **inbox_detail_payload(request, submission_id)}, 200)
