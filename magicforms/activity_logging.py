"""Record HTTP requests and model changes across the Django app and mobile API."""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from django.conf import settings
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.http import HttpRequest, HttpResponse

_request_local = threading.local()

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password1",
        "password2",
        "old_password",
        "new_password",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "api_secret",
        "csrfmiddlewaretoken",
        "authorization",
    }
)

_SKIP_PATH_PREFIXES = (
    "/static/",
    "/media/",
)

_SKIP_PATH_EXACT = frozenset(
    {
        "/favicon.ico",
        "/robots.txt",
    }
)

# Avoid logging every row while staff scroll the log UI.
_SKIP_PATH_STARTSWITH = ("/manage/activity-log",)

_MAX_JSON_BODY = 12_000


def get_current_request() -> HttpRequest | None:
    return getattr(_request_local, "request", None)


def _should_log_request(request: HttpRequest) -> bool:
    path = (request.path_info or "/")[:500]
    if path in _SKIP_PATH_EXACT:
        return False
    if any(path.startswith(p) for p in _SKIP_PATH_PREFIXES):
        return False
    if any(path.startswith(p) for p in _SKIP_PATH_STARTSWITH):
        return False
    if (request.method or "").upper() in ("OPTIONS", "HEAD"):
        return False
    return True


def _request_channel(request: HttpRequest) -> str:
    from .models import ActivityLog

    path = request.path_info or ""
    if path.startswith("/api/v1/"):
        return ActivityLog.Channel.API_MOBILE
    if path.startswith("/manage/"):
        return ActivityLog.Channel.WEB_MANAGE
    if path.startswith("/admin/"):
        return ActivityLog.Channel.WEB_MANAGE
    if path.startswith("/e/") or path.startswith("/f/"):
        return ActivityLog.Channel.WEB_PUBLIC
    return ActivityLog.Channel.WEB_OTHER


def _request_actor(request: HttpRequest) -> tuple[Any | None, str, bool]:
    user = getattr(request, "mobile_user", None)
    if user is None and getattr(request, "user", None) and request.user.is_authenticated:
        user = request.user
    if user is None:
        return None, "", False
    username = user.get_username() if hasattr(user, "get_username") else str(user)
    is_staff = bool(
        getattr(user, "is_superuser", False) or getattr(user, "is_staff", False)
    )
    return user, username[:150], is_staff


def _client_ip(request: HttpRequest) -> str | None:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:45]
    addr = request.META.get("REMOTE_ADDR")
    return str(addr)[:45] if addr else None


def _is_sensitive_key(key: str) -> bool:
    kl = key.lower()
    if kl in _SENSITIVE_KEYS:
        return True
    return any(x in kl for x in ("password", "secret", "token"))


def _redact_mapping(data: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, val in list(data.items())[:50]:
        if _is_sensitive_key(str(key)):
            out[str(key)] = "***"
            continue
        s = str(val)
        out[str(key)] = (s[:200] + "…") if len(s) > 200 else s
    return out


def _redacted_post_snapshot(request: HttpRequest) -> dict[str, str]:
    if not request.POST:
        return {}
    return _redact_mapping({k: request.POST.get(k) for k in request.POST.keys()})


def _capture_request_payload(request: HttpRequest) -> dict[str, Any]:
    """Snapshot query, form, JSON body, and uploaded field names (before view runs)."""
    payload: dict[str, Any] = {"source": "http"}
    if request.GET:
        payload["query"] = _redact_mapping(
            {k: request.GET.get(k) for k in list(request.GET.keys())[:40]}
        )
    post_snap = _redacted_post_snapshot(request)
    if post_snap:
        payload["post"] = post_snap
    if request.FILES:
        payload["files"] = list(request.FILES.keys())[:30]
    method = (request.method or "").upper()
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        ctype = (request.content_type or "").lower()
        if "json" in ctype and request.body:
            try:
                raw = request.body[:_MAX_JSON_BODY]
                parsed = json.loads(raw.decode("utf-8", errors="replace"))
                if isinstance(parsed, dict):
                    payload["json"] = _redact_mapping(
                        {k: parsed[k] for k in list(parsed.keys())[:50]}
                    )
                else:
                    payload["json"] = str(parsed)[:500]
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                payload["json"] = "(unparsed body)"
    if getattr(request, "mobile_user", None) is not None:
        payload["auth"] = "mobile_bearer"
    return payload


def _entity_id_for_request(request: HttpRequest) -> int | None:
    ent = getattr(request, "portal_entity", None)
    if ent is not None and getattr(ent, "pk", None):
        return int(ent.pk)
    path = request.path_info or ""
    from .opaque_ids import TOKEN_REGEX, decode

    match = re.search(r"/manage/(?:forms|people|organizations|organization)/(" + TOKEN_REGEX + ")", path)
    if match:
        return decode(match.group(1))
    match = re.search(r"/api/v1/(?:forms|inbox)/(\d+)", path)
    if match:
        return int(match.group(1))
    return None


def _build_summary(
    request: HttpRequest,
    *,
    status_code: int | None,
    view_name: str,
) -> str:
    method = (request.method or "GET").upper()
    path = (request.path_info or "/")[:400]
    parts = [method, path]
    if view_name:
        parts.append(f"({view_name})")
    if status_code is not None:
        parts.append(f"→ {status_code}")
    return " ".join(parts)[:500]


def _create_log_row(**fields) -> None:
    from .models import ActivityLog

    try:
        ActivityLog.objects.create(**fields)
    except Exception:
        if settings.DEBUG:
            raise


def record_request_activity(
    request: HttpRequest,
    response: HttpResponse,
    *,
    duration_ms: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if not _should_log_request(request):
        return

    user, username, is_staff = _request_actor(request)
    resolver = getattr(request, "resolver_match", None)
    view_name = ""
    app_name = ""
    if resolver is not None:
        view_name = (resolver.view_name or resolver.url_name or "")[:200]
        app_name = (resolver.app_name or "")[:80]

    status_code = getattr(response, "status_code", None)
    extra = dict(payload or _capture_request_payload(request))
    if app_name:
        extra["app_name"] = app_name

    _create_log_row(
        user=user if user and getattr(user, "pk", None) else None,
        username=username,
        is_staff_actor=is_staff,
        channel=_request_channel(request),
        http_method=(request.method or "")[:16],
        path=(request.path_info or "/")[:500],
        query_string=(request.META.get("QUERY_STRING") or "")[:500],
        status_code=status_code,
        view_name=view_name,
        summary=_build_summary(request, status_code=status_code, view_name=view_name),
        entity_id=_entity_id_for_request(request),
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
        duration_ms=duration_ms,
        extra=extra,
    )


def record_activity_event(
    *,
    request: HttpRequest | None = None,
    user=None,
    channel: str | None = None,
    summary: str,
    action: str = "",
    entity_id: int | None = None,
    object_type: str = "",
    object_id: str = "",
    extra: dict | None = None,
) -> None:
    from .models import ActivityLog

    req = request or get_current_request()
    if req is not None:
        u, username, is_staff = _request_actor(req)
        if user is None:
            user = u
    else:
        username = ""
        is_staff = False
        if user is not None:
            username = (
                user.get_username()[:150]
                if hasattr(user, "get_username")
                else str(user)[:150]
            )
            is_staff = bool(
                getattr(user, "is_superuser", False) or getattr(user, "is_staff", False)
            )

    ch = channel or (
        ActivityLog.Channel.WEB_OTHER
        if req is None
        else _request_channel(req)
    )
    ex = {"source": "model", **(extra or {})}
    _create_log_row(
        user=user if user and getattr(user, "pk", None) else None,
        username=username,
        is_staff_actor=is_staff,
        channel=ch,
        http_method="MODEL",
        path=(req.path_info if req else "")[:500],
        query_string=(req.META.get("QUERY_STRING") if req else "")[:500],
        status_code=None,
        view_name=(action or "")[:200],
        summary=summary[:500],
        entity_id=entity_id,
        object_type=object_type[:120],
        object_id=str(object_id)[:64] if object_id else "",
        ip_address=_client_ip(req) if req else None,
        user_agent=((req.META.get("HTTP_USER_AGENT") or "") if req else "")[:300],
        extra=ex,
    )


def _model_entity_id(instance) -> int | None:
    for attr in ("entity_id",):
        val = getattr(instance, attr, None)
        if val:
            return int(val)
    ent = getattr(instance, "entity", None)
    if ent is not None and getattr(ent, "pk", None):
        return int(ent.pk)
    form = getattr(instance, "form", None)
    if form is not None and getattr(form, "entity_id", None):
        return int(form.entity_id)
    submission = getattr(instance, "form_submission", None) or getattr(
        instance, "submission", None
    )
    if submission is not None:
        sub_form = getattr(submission, "form", None)
        if sub_form is not None and getattr(sub_form, "entity_id", None):
            return int(sub_form.entity_id)
    return None


def _log_model_change(instance, *, verb: str, action: str) -> None:
    from .models import ActivityLog

    model_label = instance._meta.label
    pk = getattr(instance, "pk", None)
    summary = f"{verb} {model_label}"
    if pk is not None:
        summary = f"{verb} {model_label} #{pk}"
    record_activity_event(
        summary=summary[:500],
        action=action,
        channel=ActivityLog.Channel.WEB_OTHER,
        entity_id=_model_entity_id(instance),
        object_type=model_label[:120],
        object_id=str(pk) if pk is not None else "",
    )


def _on_model_save(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    _log_model_change(
        instance,
        verb="Created" if created else "Updated",
        action="model.created" if created else "model.updated",
    )


def _on_model_delete(sender, instance, **kwargs):
    _log_model_change(instance, verb="Deleted", action="model.deleted")


def _on_m2m_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if kwargs.get("raw"):
        return
    model_label = sender._meta.label if hasattr(sender, "_meta") else str(sender)
    summary = f"M2M {action} on {model_label}"
    record_activity_event(
        summary=summary[:500],
        action=f"model.m2m.{action}",
        object_type=model_label[:120],
        object_id=str(getattr(instance, "pk", "") or ""),
        extra={"pk_set": [str(x) for x in list(pk_set or [])[:20]]},
    )


def connect_model_activity_signals() -> None:
    """Wire save/delete/M2M logging for all magicforms models (except ActivityLog)."""
    from django.apps import apps

    from .models import ActivityLog

    app_config = apps.get_app_config("magicforms")
    for model in app_config.get_models():
        if model is ActivityLog:
            continue
        label = model._meta.label_lower
        post_save.connect(
            _on_model_save,
            sender=model,
            dispatch_uid=f"magicforms.activity.save.{label}",
        )
        post_delete.connect(
            _on_model_delete,
            sender=model,
            dispatch_uid=f"magicforms.activity.delete.{label}",
        )
        for field in model._meta.many_to_many:
            m2m_changed.connect(
                _on_m2m_changed,
                sender=field.remote_field.through,
                dispatch_uid=f"magicforms.activity.m2m.{label}.{field.name}",
            )


class ActivityLogMiddleware:
    """Log every HTTP request (studio, public site, API, admin) and attach request to model logs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _request_local.request = request
        should_log = _should_log_request(request)
        payload = _capture_request_payload(request) if should_log else None
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        finally:
            _request_local.request = None
        if should_log and payload is not None:
            duration_ms = int((time.perf_counter() - started) * 1000)
            try:
                record_request_activity(
                    request,
                    response,
                    duration_ms=duration_ms,
                    payload=payload,
                )
            except Exception:
                if settings.DEBUG:
                    raise
        return response
