"""Register mobile push device tokens (APNs / FCM)."""

from __future__ import annotations

from django.utils import timezone

from magicforms.models import MobilePushDevice


def register_push_device(
    *,
    user,
    platform: str,
    token: str,
    device_id: str = "",
) -> MobilePushDevice:
    token = (token or "").strip()
    if not token:
        raise ValueError("token required")
    platform = (platform or "").strip().lower()
    if platform not in (MobilePushDevice.PLATFORM_IOS, MobilePushDevice.PLATFORM_ANDROID):
        raise ValueError("invalid platform")
    device_id = (device_id or "").strip()[:128]
    row, _created = MobilePushDevice.objects.update_or_create(
        user=user,
        platform=platform,
        token=token,
        defaults={
            "device_id": device_id,
            "is_active": True,
            "updated_at": timezone.now(),
        },
    )
    return row


def deactivate_push_devices_for_user(user, *, token: str | None = None) -> int:
    qs = MobilePushDevice.objects.filter(user=user, is_active=True)
    if token:
        qs = qs.filter(token=token.strip())
    return qs.update(is_active=False, updated_at=timezone.now())
