"""Request middleware for MagicForms."""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect

from .activity_logging import ActivityLogMiddleware

from .subdomain import (
    apply_request_host,
    best_request_host,
    fix_redirect_location_for_portal,
    reject_mismatched_portal_entity,
    resolve_portal_entity_for_request,
    subdomain_portal_enabled,
    subdomain_slug_detected,
    unknown_organization_response,
)

__all__ = [
    "ActivityLogMiddleware",
    "PortalRequestHostMiddleware",
    "EntitySubdomainMiddleware",
]

# Studio, admin, and i18n stay on the main URLconf (apex host).
_PORTAL_ROUTING_EXCLUDED_PREFIXES = (
    "/manage",
    "/admin",
    "/i18n",
    "/static",
    "/media",
    "/welcome",  # SwapForms landing page, also on the apex portal host
    "/favicon.ico",
    "/apple-touch-icon",
)


class PortalRequestHostMiddleware:
    """
    Force Django to see the browser's entity subdomain host.
    With ``USE_X_FORWARDED_HOST``, redirects use ``X-Forwarded-Host``; if nginx sends
    ``swapforms.com`` there, the subdomain is lost on the first redirect.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = best_request_host(request)
        if host:
            apply_request_host(request, host)
        response = self.get_response(request)
        return fix_redirect_location_for_portal(request, response)


class EntitySubdomainMiddleware:
    """
    Entity portals on ``{slug}.{MAGIFORM_BASE_DOMAIN}``.
    Apex ``swapforms.com`` uses the default entity (slug ``default``).
    Unknown subdomains show a 404 error page.
    Short public URLs: ``/``, ``/f/…/`` (no ``/e/<slug>/`` prefix).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.portal_entity = None
        request.portal_entity_from_subdomain = False
        request.portal_short_urls = False

        path = request.path_info or "/"

        blocked = unknown_organization_response(request)
        if blocked is not None:
            return blocked

        if not subdomain_portal_enabled():
            # Main domain only: old ``{slug}.swapforms.com`` links move permanently to ``swapforms.com/e/{slug}/…``.
            legacy = self._redirect_subdomain_to_apex(request, path)
            if legacy is not None:
                return legacy
            return self.get_response(request)

        if self._path_uses_main_urlconf(path):
            return self.get_response(request)

        entity, from_subdomain = resolve_portal_entity_for_request(request)
        if entity is None:
            return self.get_response(request)

        if reject_mismatched_portal_entity(request, entity):
            blocked = unknown_organization_response(request)
            if blocked is not None:
                return blocked

        request.portal_entity = entity
        detected = subdomain_slug_detected(request)
        request.portal_entity_from_subdomain = bool(
            from_subdomain
            or (
                detected
                and detected.lower() == entity.slug.lower()
            )
        )
        request.portal_short_urls = True
        request.urlconf = getattr(
            settings,
            "MAGIFORM_PORTAL_SUBDOMAIN_URLCONF",
            "magicforms.urls_subdomain",
        )

        redirect_response = self._redirect_legacy_entity_path(request, entity)
        if redirect_response is not None:
            return fix_redirect_location_for_portal(request, redirect_response)

        response = self.get_response(request)
        return fix_redirect_location_for_portal(request, response)

    def _redirect_subdomain_to_apex(self, request, path: str):
        from .subdomain import base_domain, split_host_port, subdomain_slug_detected

        slug = subdomain_slug_detected(request)
        domain = base_domain()
        if not slug or not domain:
            return None
        scheme = "https" if request.is_secure() else "http"
        _host, port = split_host_port(request.get_host())
        port_bit = f":{port}" if port and port not in ("80", "443") else ""
        apex = f"{scheme}://{domain}{port_bit}"
        qs = request.META.get("QUERY_STRING", "")
        if self._path_uses_main_urlconf(path) or path.startswith("/e/") or path.startswith("/welcome"):
            target = f"{apex}{path}"
        else:
            target = f"{apex}/e/{slug}{path}"
        if qs:
            target = f"{target}?{qs}"
        return redirect(target, permanent=True)

    def _path_uses_main_urlconf(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in _PORTAL_ROUTING_EXCLUDED_PREFIXES)

    def _redirect_legacy_entity_path(self, request, entity):
        path = request.path_info or "/"
        prefix = f"/e/{entity.slug}"
        if path == prefix or path == prefix + "/":
            qs = request.META.get("QUERY_STRING", "")
            target = "/" + (f"?{qs}" if qs else "")
            return redirect(target)
        if path.startswith(prefix + "/"):
            new_path = path[len(prefix) :] or "/"
            qs = request.META.get("QUERY_STRING", "")
            if qs:
                new_path = f"{new_path}?{qs}" if "?" not in new_path else f"{new_path}&{qs}"
            return redirect(new_path)
        return None


class SuperuserOrganizationScopeMiddleware:
    """
    Super admins must pick an organization before using the studio.

    After sign-in the session has no scope; every /manage/ request is redirected to the chooser
    until one is stored (the chooser posts to ``manage:superuser_entity_scope``). Login, logout,
    the chooser and the scope endpoint stay reachable. Other users are unaffected.
    """

    EXEMPT_URL_NAMES = {"login", "logout", "choose_organization", "superuser_entity_scope"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_superuser:
            from django.urls import reverse
            from .entity_access import MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY

            match = getattr(request, "resolver_match", None)
            if match is None:
                from django.urls import resolve, Resolver404

                try:
                    match = resolve(request.path_info)
                except Resolver404:
                    match = None
            if (
                match is not None
                and match.namespace == "manage"
                and match.url_name not in self.EXEMPT_URL_NAMES
                and MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY not in request.session
            ):
                from django.http import HttpResponseRedirect
                from urllib.parse import urlencode

                chooser = reverse("manage:choose_organization")
                nxt = request.get_full_path()
                return HttpResponseRedirect(f"{chooser}?{urlencode({'next': nxt})}")
        return self.get_response(request)
