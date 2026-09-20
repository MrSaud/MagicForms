from __future__ import annotations

from typing import Any

from django.conf import settings


def ai_features_enabled() -> bool:
    """AI assistance (Create with AI, inbox assistant) is opt-in via MAGIFORM_AI_FEATURES_ENABLED."""
    return bool(getattr(settings, "MAGIFORM_AI_FEATURES_ENABLED", False))


def applicant_related_pending(request) -> dict[str, Any]:
    """
    Adds ``applicant_related_pending_count`` for signed-in users who owe related (child) forms.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_active:
        return {"applicant_related_pending_count": 0}
    from .supplementary import related_pending_count_for_user

    return {"applicant_related_pending_count": related_pending_count_for_user(user)}


def portal_subdomain(request) -> dict[str, Any]:
    from magicforms.entity_branding import entity_logo_url, resolve_manage_banner_entity

    banner_entity = getattr(request, "portal_entity", None) or resolve_manage_banner_entity(
        request
    )
    logo_url = entity_logo_url(banner_entity, request)
    return {
        "portal_on_subdomain": bool(getattr(request, "portal_entity_from_subdomain", False)),
        "portal_short_urls": bool(getattr(request, "portal_short_urls", False)),
        "portal_entity_subdomain": getattr(request, "portal_entity", None),
        "banner_entity": banner_entity,
        "banner_logo_url": logo_url,
        "banner_logo_alt": (banner_entity.name if banner_entity else "SwapForms"),
    }


def portal_studio_urls(request) -> dict[str, Any]:
    """
    Studio links for public templates. On entity subdomains the active urlconf has no
    ``manage:`` namespace, so use absolute apex URLs.
    """
    from urllib.parse import urlencode

    from django.urls import reverse

    from .subdomain import (
        apex_site_url,
        on_portal_subdomain_urlconf,
        portal_return_url,
        studio_login_next_url,
        studio_login_url,
        studio_manage_url,
    )

    apex_base = apex_site_url(request).rstrip("/")

    if on_portal_subdomain_urlconf(request):
        dashboard = studio_manage_url(request, "/manage/")
        login = studio_login_url(request)
        inbox = studio_manage_url(request, "/manage/inbox/")
        task_list = studio_manage_url(request, "/manage/tasks/")
        submission_search = studio_manage_url(request, "/manage/submissions/search/")
        i18n_set_language = "/i18n/setlang/"
        portal_home = "/"
    else:
        dashboard = reverse("manage:dashboard")
        login = reverse("manage:login")
        inbox = reverse("manage:inbox")
        task_list = reverse("manage:task_list")
        submission_search = reverse("manage:submission_search")
        i18n_set_language = reverse("set_language")
        portal_home = reverse("magicforms:home")

    return_url = portal_return_url(request)

    return {
        "studio_dashboard_url": dashboard,
        "studio_login_url": login,
        "studio_inbox_url": inbox,
        "studio_task_list_url": task_list,
        "studio_submission_search_url": submission_search,
        "studio_login_next_dashboard": f"{login}?{urlencode({'next': dashboard})}",
        "studio_login_next_here": studio_login_next_url(request, return_url),
        "studio_login_next_submission_search": studio_login_next_url(request, submission_search),
        "i18n_set_language_url": i18n_set_language,
        "apex_public_home_url": f"{apex_base}/",
        "portal_home_url": portal_home,
        "landing_page_url": "/welcome/",
        "ai_features_enabled": ai_features_enabled(),
    }


def manage_studio_nav(request) -> dict[str, Any]:
    """Inbox badge (portal users), organization line, superuser scope, and portal availability."""
    from .entity_access import (
        MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY,
        entities_queryset_for_user,
        entity_ids_for_user,
    )
    from .models import Entity
    from .submission_tasks import open_task_count_for_user
    from .workflow_access import inbox_open_count_for_user

    user = getattr(request, "user", None)
    from .entity_permissions import ENTITY_PERMISSIONS, PERMISSION_AREAS

    ctx: dict[str, Any] = {
        "manage_inbox_count": 0,
        "manage_open_task_count": 0,
        "manage_header_entities": [],
        "manage_scope_entities": [],
        "manage_scope_selected_ids": [],
        "manage_scope_selected_id": None,
        "manage_scope_is_all": False,
        "studio_available": False,
    }
    for area, _label in PERMISSION_AREAS:
        ctx[f"manage_can_{area}"] = False
    for perm in ENTITY_PERMISSIONS:
        ctx[f"manage_can_{perm}"] = False
    if not user or not user.is_authenticated or not user.is_active:
        return ctx

    from .entity_permissions import user_has_any_entity_permission, user_has_any_entity_read

    for area, _label in PERMISSION_AREAS:
        ctx[f"manage_can_{area}"] = user_has_any_entity_read(user, area, request=request)
    for perm in ENTITY_PERMISSIONS:
        ctx[f"manage_can_{perm}"] = user_has_any_entity_permission(user, perm, request=request)

    has_portal = user.is_superuser or bool(entity_ids_for_user(user))
    ctx["studio_available"] = bool(has_portal)
    if has_portal:
        ctx["manage_inbox_count"] = inbox_open_count_for_user(user, request)
        ctx["manage_open_task_count"] = open_task_count_for_user(user)

    ctx["manage_header_entities"] = list(entities_queryset_for_user(user, request))

    if user.is_superuser:
        ctx["manage_scope_entities"] = list(Entity.objects.order_by("name"))
        scope = request.session.get(MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY, "all")
        selected_id = None
        if scope == "all" or scope is None:
            ctx["manage_scope_is_all"] = True
        elif isinstance(scope, int):
            if Entity.objects.filter(pk=scope).exists():
                selected_id = scope
                ctx["manage_scope_is_all"] = False
            else:
                ctx["manage_scope_is_all"] = True
        elif isinstance(scope, list):
            raw = [int(x) for x in scope if str(x).isdigit()]
            if raw and Entity.objects.filter(pk=raw[0]).exists():
                selected_id = raw[0]
                ctx["manage_scope_is_all"] = False
            else:
                ctx["manage_scope_is_all"] = True
        else:
            ctx["manage_scope_is_all"] = True
        ctx["manage_scope_selected_id"] = selected_id
        ctx["manage_scope_selected_ids"] = [selected_id] if selected_id else []
        ctx["manage_scope_selected_name"] = (
            next((e.name for e in ctx["manage_scope_entities"] if e.pk == selected_id), "") if selected_id else ""
        )
    return ctx
