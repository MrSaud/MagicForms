"""
Push notification helpers for native apps.

Delivery requires APNs / FCM credentials configured in your environment.
This module stores device tokens and exposes hooks you can call from workflow
events when you wire a provider (e.g. django-push, firebase-admin).
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def push_enabled() -> bool:
    return bool(getattr(settings, "MOBILE_PUSH_ENABLED", False))


def notify_user(
    user,
    *,
    title: str,
    body: str,
    data: dict | None = None,
) -> int:
    """
    Send a push to all active devices for ``user``.

    Returns the number of devices targeted (0 when push is disabled or no tokens).
  """
    from magicforms.models import MobilePushDevice

    if not push_enabled():
        logger.debug("mobile push skipped (MOBILE_PUSH_ENABLED is false)")
        return 0

    devices = list(
        MobilePushDevice.objects.filter(user=user, is_active=True).values_list(
            "platform", "token", named=True
        )
    )
    if not devices:
        return 0

    for device in devices:
        _deliver_stub(device.platform, device.token, title=title, body=body, data=data or {})

    return len(devices)


def _deliver_stub(platform: str, token: str, *, title: str, body: str, data: dict) -> None:
    """Replace with APNs/FCM integration when credentials are available."""
    logger.info(
        "mobile push stub platform=%s token=%s… title=%r",
        platform,
        token[:12] if len(token) > 12 else token,
        title,
    )


def notify_inbox_assignment(user, submission) -> int:
    form_title = getattr(getattr(submission, "form", None), "title", "") or "Request"
    return notify_user(
        user,
        title="Action needed",
        body=f"{form_title} needs your review.",
        data={"type": "inbox", "submission_id": submission.pk},
    )


def notify_thread_reply(user, submission) -> int:
    form_title = getattr(getattr(submission, "form", None), "title", "") or "Request"
    return notify_user(
        user,
        title="New message",
        body=f"Reply on {form_title}.",
        data={"type": "thread", "submission_id": submission.pk},
    )


def notify_pending_related(user, count: int) -> int:
    if count < 1:
        return 0
    label = "form" if count == 1 else "forms"
    return notify_user(
        user,
        title="Forms to complete",
        body=f"You have {count} {label} waiting.",
        data={"type": "related_pending"},
    )
