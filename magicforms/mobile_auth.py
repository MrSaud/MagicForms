"""Mobile API authentication (directory + Django password, bearer tokens)."""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.utils import timezone

from .entity_access import entity_ids_for_user
from .login_api import entities_with_active_login_api, resolve_login_entity, try_directory_login_or_none
from .login_identity import parse_login_identity
from .models import Entity, MobileAuthToken
from .studio_login import _directory_login_applies_to_username


def mobile_token_ttl() -> timedelta:
    seconds = int(getattr(settings, "MOBILE_API_TOKEN_TTL_SECONDS", 60 * 60 * 24 * 30))
    return timedelta(seconds=max(3600, seconds))


def _entity_choices_payload() -> list[dict[str, str]]:
    return [{"slug": e.slug, "name": e.name} for e in entities_with_active_login_api()]


def authenticate_for_mobile(
    *,
    username: str,
    password: str,
    entity_slug: str = "",
) -> tuple[object | None, str, str | None, list[dict[str, str]] | None]:
    """
  Authenticate a user for the mobile API.

  Returns ``(user, login_via, error_code, entity_choices)``.
  ``login_via`` is ``directory`` or ``password``.
  ``error_code`` is ``organization_required`` when multiple directory orgs need a slug.
  """
    User = get_user_model()
    username = (username or "").strip()
    password = password or ""
    entity_slug = (entity_slug or "").strip()
    if not username or not password:
        return None, "", "invalid_credentials", None

    api_entities = list(entities_with_active_login_api())
    if not entity_slug:
        parsed = parse_login_identity(username, [e.slug for e in api_entities])
        username = parsed.username
        entity_slug = (parsed.entity_slug or "").strip()

    if len(api_entities) > 1 and not entity_slug and _directory_login_applies_to_username(username):
        return None, "", "organization_required", _entity_choices_payload()

    post_data = {"login_entity_slug": entity_slug}
    entity = resolve_login_entity(post_data, {})

    if entity is not None and _directory_login_applies_to_username(username):
        user = try_directory_login_or_none(entity, username, password)
        if user is not None:
            if not user.is_active:
                return None, "", "inactive_account", None
            return user, "directory", None, None
        return None, "", "invalid_credentials", None

    user = authenticate(username=username, password=password)
    if user is None or not user.is_active:
        return None, "", "invalid_credentials", None
    return user, "password", None, None


def user_may_use_mobile_api(user) -> bool:
    """Active users with studio portal access (entity member or superuser)."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if user.is_superuser:
        return True
    ids = entity_ids_for_user(user)
    return bool(ids)


def entities_for_mobile_user(user, request=None) -> list[dict[str, str | int]]:
    from magicforms.entity_branding import entities_for_mobile_user_payload

    return entities_for_mobile_user_payload(user, request)


def user_payload(user) -> dict:
    return {
        "id": user.pk,
        "username": user.get_username(),
        "email": user.email or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "full_name": (user.get_full_name() or "").strip(),
        "is_staff": bool(user.is_staff),
        "is_superuser": bool(user.is_superuser),
    }


def create_mobile_token(user) -> MobileAuthToken:
    now = timezone.now()
    expires = now + mobile_token_ttl()
    return MobileAuthToken.objects.create(
        user=user,
        key=secrets.token_urlsafe(48),
        expires_at=expires,
    )


def revoke_mobile_token(raw_key: str) -> bool:
    key = (raw_key or "").strip()
    if not key:
        return False
    deleted, _ = MobileAuthToken.objects.filter(key=key).delete()
    return deleted > 0


def user_from_mobile_token(raw_key: str):
    key = (raw_key or "").strip()
    if not key:
        return None
    now = timezone.now()
    try:
        row = MobileAuthToken.objects.select_related("user").get(key=key)
    except MobileAuthToken.DoesNotExist:
        return None
    if row.expires_at <= now:
        row.delete()
        return None
    user = row.user
    if not user.is_active:
        return None
    MobileAuthToken.objects.filter(pk=row.pk).update(last_used_at=now)
    return user


def bearer_token_from_request(request) -> str:
    auth = (request.META.get("HTTP_AUTHORIZATION") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""
