"""Mobile API helpers for user signature images."""

from __future__ import annotations

from django.db.models import Max
from django.http import Http404, HttpRequest
from django.utils import timezone
from django.utils.dateformat import format as date_format

from magicforms.models import USER_SIGNATURE_MAX_PER_USER, UserSignature


def _mobile_user(request: HttpRequest):
    return getattr(request, "mobile_user", None)


def _iso_dt(dt) -> str:
    if not dt:
        return ""
    return timezone.localtime(dt).isoformat()


def _dt_label(dt) -> str:
    if not dt:
        return ""
    return date_format(timezone.localtime(dt), "M j, Y")


def serialize_signature(request: HttpRequest, sig: UserSignature, *, is_primary: bool) -> dict:
    image_url = ""
    if sig.image:
        image_url = request.build_absolute_uri(sig.image.url)
    return {
        "id": sig.pk,
        "label": sig.label or "",
        "image_url": image_url,
        "is_primary": is_primary,
        "sort_order": sig.sort_order,
        "created_at": _iso_dt(sig.created_at),
        "created_at_label": _dt_label(sig.created_at),
    }


def signatures_list_payload(request: HttpRequest) -> dict:
    user = _mobile_user(request)
    sigs = list(user.signatures.order_by("sort_order", "id"))
    primary_pk = sigs[0].pk if sigs else None
    return {
        "limit": USER_SIGNATURE_MAX_PER_USER,
        "count": len(sigs),
        "signatures": [
            serialize_signature(request, s, is_primary=(s.pk == primary_pk)) for s in sigs
        ],
    }


def _get_user_signature(request: HttpRequest, signature_id: int) -> UserSignature:
    user = _mobile_user(request)
    sig = UserSignature.objects.filter(user=user, pk=signature_id).first()
    if sig is None:
        raise Http404
    return sig


def _next_sort_order(user) -> int:
    mx = user.signatures.aggregate(mx=Max("sort_order"))["mx"]
    return (mx if mx is not None else -1) + 1


def create_signature_from_upload(request: HttpRequest, *, label: str = "") -> UserSignature:
    user = _mobile_user(request)
    if user.signatures.count() >= USER_SIGNATURE_MAX_PER_USER:
        raise ValueError("limit_reached")
    image = request.FILES.get("image")
    if not image:
        raise ValueError("image_required")
    sig = UserSignature(user=user, label=(label or "")[:120])
    sig.image = image
    sig.sort_order = _next_sort_order(user)
    sig.save()
    return sig


def replace_signature_image(request: HttpRequest, signature_id: int) -> UserSignature:
    sig = _get_user_signature(request, signature_id)
    image = request.FILES.get("image")
    if not image:
        raise ValueError("image_required")
    sig.image = image
    sig.save()
    return sig


def update_signature_label(request: HttpRequest, signature_id: int, label: str) -> UserSignature:
    sig = _get_user_signature(request, signature_id)
    sig.label = (label or "")[:120]
    sig.save(update_fields=["label"])
    return sig


def delete_signature(request: HttpRequest, signature_id: int) -> bool:
    user = _mobile_user(request)
    deleted, _ = user.signatures.filter(pk=signature_id).delete()
    return deleted > 0


def set_primary_signature(request: HttpRequest, signature_id: int) -> bool:
    user = _mobile_user(request)
    return UserSignature.assign_primary(user, signature_id)
