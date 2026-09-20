"""Entity portal hostnames: ``{entity.slug}.{MAGIFORM_BASE_DOMAIN}``."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse

_HOST_PORT_RE = re.compile(r"^(.+):(\d+)$")


def subdomain_portal_enabled() -> bool:
    return bool((getattr(settings, "MAGIFORM_BASE_DOMAIN", "") or "").strip()) and getattr(
        settings, "MAGIFORM_SUBDOMAIN_PORTAL_ENABLED", True
    )


def base_domain() -> str:
    return (getattr(settings, "MAGIFORM_BASE_DOMAIN", "") or "").strip().lower()


def _base_domain_from_allowed_hosts() -> str | None:
    for entry in getattr(settings, "ALLOWED_HOSTS", ()):
        raw = (entry or "").strip().lower()
        if raw.startswith(".") and raw.count(".") >= 2:
            return raw[1:]
    return None


def effective_base_domain(host: str = "") -> str | None:
    """
    Portal base domain from ``MAGIFORM_BASE_DOMAIN``, ``ALLOWED_HOSTS`` (``.swapforms.com``),
    or the request host (``{slug}.swapforms.com`` → ``swapforms.com``).
    """
    configured = base_domain()
    if configured:
        return configured
    from_allowed = _base_domain_from_allowed_hosts()
    if from_allowed:
        return from_allowed
    hostname, _port = split_host_port(host)
    if not hostname or hostname in ("localhost", "127.0.0.1"):
        return None
    parts = hostname.split(".")
    if len(parts) >= 3:
        return ".".join(parts[-2:])
    if len(parts) == 2 and parts[0] not in ("www",):
        return hostname
    return None


def split_host_port(host: str) -> tuple[str, str | None]:
    host = (host or "").split("@")[-1].strip().lower()
    if not host:
        return "", None
    m = _HOST_PORT_RE.match(host)
    if m:
        return m.group(1), m.group(2)
    return host, None


def portal_base_domains() -> list[str]:
    """Registered portal apex domains (``swapforms.com``, settings, ALLOWED_HOSTS)."""
    domains: list[str] = []
    for candidate in (base_domain(), _base_domain_from_allowed_hosts()):
        if candidate and candidate not in domains:
            domains.append(candidate)
    return domains


def _aggressive_subdomain_slug(host: str) -> str | None:
    """Parse ``{slug}.swapforms.com`` even when other host helpers return nothing."""
    hostname, _port = split_host_port(host)
    if not hostname:
        return None
    for domain in portal_base_domains():
        suffix = f".{domain}"
        if not hostname.endswith(suffix):
            continue
        slug = hostname[: -len(suffix)]
        if slug and slug not in ("www",) and "." not in slug:
            return slug
    return None


def best_request_host(request: HttpRequest) -> str | None:
    """
    Host header Django should use for redirects and absolute URLs.
    When proxy sends both ``default.swapforms.com`` and ``swapforms.com``, prefer the subdomain.
    """
    candidates: list[str] = []
    for key in (
        "HTTP_X_PORTAL_HOST",
        "HTTP_X_FORWARDED_HOST",
        "HTTP_X_ORIGINAL_HOST",
        "HTTP_HOST",
    ):
        raw = request.META.get(key) or ""
        for part in raw.split(","):
            part = part.strip()
            if part and part not in candidates:
                candidates.append(part)
    for host in candidates:
        hostname, _port = split_host_port(host)
        if entity_slug_from_host(host) or _aggressive_subdomain_slug(hostname):
            return host
    return candidates[0] if candidates else None


def apply_request_host(request: HttpRequest, host: str) -> None:
    """Normalize proxy host headers (``USE_X_FORWARDED_HOST`` reads X-Forwarded-Host)."""
    request.META["HTTP_HOST"] = host
    request.META["HTTP_X_FORWARDED_HOST"] = host
    request.META["HTTP_X_PORTAL_HOST"] = host


def request_host_candidates(request: HttpRequest) -> list[str]:
    """
    Hostnames to evaluate for portal routing (proxy may send the subdomain only in
    ``X-Portal-Host`` / ``X-Forwarded-Host`` while ``Host`` is the apex).
    """
    hosts: list[str] = []
    for key in (
        "HTTP_X_PORTAL_HOST",
        "HTTP_X_FORWARDED_HOST",
        "HTTP_X_ORIGINAL_HOST",
        "HTTP_HOST",
    ):
        raw = request.META.get(key) or ""
        for part in raw.split(","):
            part = split_host_port(part.strip())[0]
            if part and part not in hosts:
                hosts.append(part)
    try:
        resolved = split_host_port(request.get_host())[0]
        if resolved and resolved not in hosts:
            hosts.append(resolved)
    except Exception:
        pass
    return hosts


def subdomain_slug_detected(request: HttpRequest) -> str | None:
    """Subdomain label from any trusted host header (``fff`` for ``fff.swapforms.com``)."""
    for host in request_host_candidates(request):
        slug = entity_slug_from_host(host) or _aggressive_subdomain_slug(host)
        if slug:
            return slug
    return None


def entity_slug_from_request(request: HttpRequest) -> str | None:
    return subdomain_slug_detected(request)


def primary_portal_hostname(request: HttpRequest) -> str:
    """Best single hostname for this request (portal header first)."""
    for key in ("HTTP_X_PORTAL_HOST", "HTTP_X_FORWARDED_HOST", "HTTP_HOST"):
        raw = request.META.get(key) or ""
        if raw:
            return split_host_port(raw.split(",")[0].strip())[0]
    try:
        return split_host_port(request.get_host())[0]
    except Exception:
        return ""


def request_is_apex_portal(request: HttpRequest) -> bool:
    return any(is_apex_portal_host(host) for host in request_host_candidates(request))


def is_strict_apex_portal_request(request: HttpRequest) -> bool:
    """Default-entity portal only on ``swapforms.com`` / ``www`` — never on ``{slug}.…``."""
    if subdomain_slug_detected(request):
        return False
    primary = primary_portal_hostname(request)
    return bool(primary) and is_apex_portal_host(primary)


def entity_slug_from_host(host: str, *, require_portal_enabled: bool = False) -> str | None:
    """
    Return entity slug when ``host`` is ``{slug}.{base_domain}``.
    Apex ``base_domain``, ``www``, and bare localhost are not entity hosts.
    """
    if require_portal_enabled and not subdomain_portal_enabled():
        return None
    domain = effective_base_domain(host)
    if not domain:
        return None
    hostname, _port = split_host_port(host)
    if hostname in (domain, f"www.{domain}"):
        return None
    suffix = f".{domain}"
    if not hostname.endswith(suffix):
        return None
    slug = hostname[: -len(suffix)]
    if not slug or "." in slug:
        return None
    return slug


def default_entity_slug() -> str:
    return (getattr(settings, "MAGIFORM_DEFAULT_ENTITY_SLUG", "") or "default").strip()


def get_default_portal_entity():
    from .models import Entity

    slug = default_entity_slug()
    if not slug:
        return None
    return Entity.objects.filter(is_active=True, slug__iexact=slug).first()


def is_apex_portal_host(host: str) -> bool:
    """``swapforms.com`` / ``www.swapforms.com`` (not an entity subdomain)."""
    domain = effective_base_domain(host)
    if not domain:
        return False
    hostname, _port = split_host_port(host)
    return hostname in (domain, f"www.{domain}")


def entity_from_request_host(request: HttpRequest):
    from .models import Entity

    slug = entity_slug_from_request(request)
    if not slug:
        return None
    return Entity.objects.filter(is_active=True, slug__iexact=slug).first()


def unknown_entity_subdomain_slug(request: HttpRequest) -> str | None:
    """Host has ``{slug}.{base_domain}`` but no active organization with that slug."""
    from .models import Entity

    slug = subdomain_slug_detected(request)
    if not slug:
        return None
    if Entity.objects.filter(is_active=True, slug__iexact=slug).exists():
        return None
    return slug


def reject_mismatched_portal_entity(request: HttpRequest, entity) -> bool:
    """
    True when the bound portal entity does not match the subdomain in the host headers
    (e.g. default org incorrectly served on ``fff.swapforms.com``).
    """
    if entity is None:
        return False
    detected = subdomain_slug_detected(request)
    if not detected:
        return False
    return entity.slug.lower() != detected.lower()


def unknown_organization_response(request: HttpRequest):
    """404 page when the subdomain is not a registered organization slug."""
    from django.shortcuts import render

    slug = unknown_entity_subdomain_slug(request)
    if not slug:
        return None
    return render(
        request,
        "magicforms/unknown_organization.html",
        {
            "subdomain_slug": slug,
            "apex_site_url": apex_site_url(request),
        },
        status=404,
    )


def on_portal_subdomain_urlconf(request: HttpRequest | None) -> bool:
    """Public portal is using ``urls_subdomain`` (no ``manage:`` URL namespace)."""
    if not request:
        return False
    if getattr(request, "portal_short_urls", False):
        return True
    urlconf = getattr(request, "urlconf", None)
    return bool(urlconf and "urls_subdomain" in str(urlconf))


def studio_manage_absolute_uri(request: HttpRequest | None, path: str) -> str:
    """Studio path on the apex host (``https://swapforms.com/manage/…``)."""
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{apex_site_url(request).rstrip('/')}{path}"


def studio_login_url(request: HttpRequest | None = None) -> str:
    """Login path on the current portal host when already on an entity subdomain."""
    if request and (
        on_portal_subdomain_urlconf(request) or subdomain_slug_detected(request)
    ):
        return "/manage/login/"
    return studio_manage_absolute_uri(request, "/manage/login/")


def studio_manage_url(request: HttpRequest | None, path: str) -> str:
    """``/manage/…`` on the current host for entity portals; apex URL otherwise."""
    if not path.startswith("/"):
        path = f"/{path}"
    if request and (
        on_portal_subdomain_urlconf(request) or subdomain_slug_detected(request)
    ):
        return path
    return studio_manage_absolute_uri(request, path)


def portal_return_url(request: HttpRequest) -> str:
    """URL to return to after studio login (keeps entity subdomain in ``next``)."""
    path = request.get_full_path()
    detected = subdomain_slug_detected(request)
    if detected and base_domain():
        return portal_origin_for_slug(detected, request).rstrip("/") + path
    return request.build_absolute_uri(path)


def studio_login_next_url(request: HttpRequest, next_url: str) -> str:
    from urllib.parse import urlencode

    return f"{studio_login_url(request)}?{urlencode({'next': next_url})}"


def apex_site_url(request: HttpRequest | None = None) -> str:
    """Base URL for the apex host (``https://swapforms.com``)."""
    host = ""
    if request:
        candidates = request_host_candidates(request)
        host = candidates[0] if candidates else request.get_host()
    domain = effective_base_domain(host)
    if not domain:
        return "/"
    scheme = "https"
    if request:
        scheme = "https" if request.is_secure() else "http"
    _host, port = split_host_port(host)
    port_bit = f":{port}" if port and port not in ("80", "443") else ""
    return f"{scheme}://{domain}{port_bit}"


def resolve_portal_entity_for_request(request: HttpRequest):
    """
    Entity for this request: subdomain match, else default entity on apex only.
    Returns ``(entity, from_subdomain)`` or ``(None, False)``.
    Unknown subdomains return ``(None, False)``; use ``unknown_entity_subdomain_slug()``.
    """
    entity = entity_from_request_host(request)
    if entity is not None:
        return entity, True
    if not subdomain_portal_enabled():
        return None, False
    if subdomain_slug_detected(request):
        return None, False
    if is_strict_apex_portal_request(request):
        return get_default_portal_entity(), False
    return None, False


def _entity_slug_kw(entity: Any, entity_slug: str | None) -> str | None:
    if entity_slug:
        return entity_slug
    if entity is None:
        return None
    if hasattr(entity, "slug"):
        return str(entity.slug)
    return str(entity)


def _portal_subdomain_urlconf() -> str:
    return getattr(settings, "MAGIFORM_PORTAL_SUBDOMAIN_URLCONF", "magicforms.urls_subdomain")


def _view_name_for_subdomain_urlconf(viewname: str) -> str:
    """
    ``urls_subdomain`` is used as a root urlconf (not via ``include()``), so reverse
    must use bare names like ``entity_home``, not ``magicforms:entity_home``.
    """
    if ":" in viewname:
        namespace, name = viewname.split(":", 1)
        if namespace == "magicforms":
            return name
    return viewname


def portal_origin_for_slug(slug: str, request: HttpRequest | None = None) -> str:
    """``https://{slug}.{MAGIFORM_BASE_DOMAIN}`` — does not use the proxy ``Host`` header."""
    slug = (slug or "").strip()
    domain = base_domain()
    if not domain and request:
        domain = effective_base_domain(primary_portal_hostname(request))
    if not slug or not domain:
        return ""
    scheme = "https"
    if request:
        scheme = "https" if request.is_secure() else "http"
    hostname = f"{slug}.{domain}"
    if request:
        _host, port = split_host_port(primary_portal_hostname(request))
        if port and port not in ("80", "443"):
            return f"{scheme}://{hostname}:{port}"
    return f"{scheme}://{hostname}"


def use_subdomain_urls(request: HttpRequest | None, entity_slug: str | None) -> bool:
    """
    Use short portal paths (``/f/…/``) for this entity.
    True on ``{slug}.swapforms.com`` even if middleware did not set ``portal_short_urls``.
    """
    if not request or not subdomain_portal_enabled():
        return False
    detected = subdomain_slug_detected(request)
    portal_entity = getattr(request, "portal_entity", None)
    slug = entity_slug or (portal_entity.slug if portal_entity else None) or detected
    if not slug:
        return False
    if entity_slug and detected and entity_slug.lower() != detected.lower():
        return False
    if detected and slug.lower() == detected.lower():
        return True
    if getattr(request, "portal_short_urls", False) and portal_entity:
        if entity_slug and entity_slug.lower() != portal_entity.slug.lower():
            return False
        return True
    return False


def request_on_entity_subdomain(request: HttpRequest | None, entity) -> bool:
    """True when the browser host is this entity's subdomain (``{slug}.swapforms.com``)."""
    if not request or entity is None:
        return False
    detected = subdomain_slug_detected(request)
    if not detected:
        return False
    return detected.lower() == str(getattr(entity, "slug", "") or "").lower()


def portal_path_for_entity(
    viewname: str,
    *,
    entity: Any = None,
    entity_slug: str | None = None,
    args=None,
    **kwargs,
) -> str:
    """
    Path for a specific entity's public portal (``/f/…`` on subdomains, else ``/e/{slug}/…``).
    Use when building absolute URLs for that entity regardless of the current request host.
    """
    kwargs = dict(kwargs)
    slug = _entity_slug_kw(entity, entity_slug or kwargs.get("entity_slug"))
    kwargs.pop("entity_slug", None)
    if slug and subdomain_portal_enabled() and base_domain():
        return reverse(
            _view_name_for_subdomain_urlconf(viewname),
            args=args,
            kwargs=kwargs,
            urlconf=_portal_subdomain_urlconf(),
        )
    if slug:
        kwargs.setdefault("entity_slug", slug)
    return reverse(viewname, args=args, kwargs=kwargs)


def portal_reverse(
    request: HttpRequest | None,
    viewname: str,
    *,
    entity: Any = None,
    entity_slug: str | None = None,
    args=None,
    kwargs=None,
) -> str:
    """Reverse a public portal URL (path-only), using subdomain routes when on an entity host."""
    kwargs = dict(kwargs or {})
    portal_entity = getattr(request, "portal_entity", None) if request else None
    if entity_slug:
        kwargs.setdefault("entity_slug", entity_slug)
    elif entity is not None:
        slug = _entity_slug_kw(entity, None)
        if slug:
            kwargs.setdefault("entity_slug", slug)
    elif portal_entity is not None:
        kwargs.setdefault("entity_slug", portal_entity.slug)

    slug_for_check = kwargs.get("entity_slug")
    if use_subdomain_urls(request, slug_for_check):
        kwargs = {k: v for k, v in kwargs.items() if k != "entity_slug"}
        return reverse(
            _view_name_for_subdomain_urlconf(viewname),
            args=args,
            kwargs=kwargs,
            urlconf=_portal_subdomain_urlconf(),
        )

    return reverse(viewname, args=args, kwargs=kwargs)


def entity_portal_base_url(entity, request: HttpRequest | None = None) -> str:
    """``https://{slug}.{base_domain}`` when configured, else path prefix on current host."""
    slug = getattr(entity, "slug", None) or ""
    domain = base_domain()
    if subdomain_portal_enabled() and domain and slug:
        return portal_origin_for_slug(slug, request)
    if request:
        return request.build_absolute_uri(f"/e/{slug}/").rstrip("/")
    return f"/e/{slug}/"


def portal_absolute_uri(
    request: HttpRequest | None,
    viewname: str,
    *,
    entity: Any = None,
    entity_slug: str | None = None,
    query: dict[str, str] | None = None,
    args=None,
    **kwargs,
) -> str:
    kwargs.pop("args", None)
    slug = _entity_slug_kw(entity, entity_slug or kwargs.get("entity_slug"))
    path = portal_path_for_entity(
        viewname, entity=entity, entity_slug=slug, args=args, **kwargs
    )
    if request and use_subdomain_urls(request, slug):
        # Build from entity slug, not request.get_host() (proxy often sends apex Host).
        origin_slug = subdomain_slug_detected(request) or slug
        if origin_slug and base_domain():
            url = portal_origin_for_slug(origin_slug, request).rstrip("/") + path
        else:
            url = path
    elif slug and subdomain_portal_enabled() and base_domain():
        ent = entity if entity is not None else type("_E", (), {"slug": slug})()
        url = entity_portal_base_url(ent, request).rstrip("/") + path
    else:
        url = request.build_absolute_uri(path) if request else path
    if query:
        q = urlencode({k: v for k, v in query.items() if v})
        if q:
            url = f"{url}{'&' if '?' in url else '?'}{q}"
    return url


def portal_redirect(
    request: HttpRequest,
    viewname: str,
    *,
    permanent: bool = False,
    entity: Any = None,
    **kwargs,
):
    from django.shortcuts import redirect

    slug = _entity_slug_kw(entity, kwargs.get("entity_slug"))
    path = portal_reverse(request, viewname, entity=entity, kwargs=kwargs)
    if request and use_subdomain_urls(request, slug):
        origin_slug = subdomain_slug_detected(request) or slug
        if origin_slug and base_domain():
            target = portal_origin_for_slug(origin_slug, request).rstrip("/") + path
            return redirect(target, permanent=permanent)
    return redirect(path, permanent=permanent)


def _location_path(location: str) -> str:
    if location.startswith("/"):
        return location.split("?", 1)[0]
    if location.startswith("http://") or location.startswith("https://"):
        from urllib.parse import urlparse

        return urlparse(location).path or ""
    return ""


def fix_redirect_location_for_portal(request: HttpRequest, response):
    """Rewrite ``Location`` when Django built an apex URL but the user is on an entity subdomain."""
    if not hasattr(response, "headers"):
        return response
    location = response.headers.get("Location")
    if not location:
        return response
    # Studio may redirect to apex on purpose; never pull ``/manage/`` back onto the subdomain.
    if _location_path(location).startswith("/manage"):
        return response
    if not subdomain_portal_enabled():
        # Main-domain mode: redirects to the apex are the whole point; leave them alone.
        return response
    detected = subdomain_slug_detected(request)
    if not detected or not base_domain():
        return response
    origin = portal_origin_for_slug(detected, request).rstrip("/")
    apex = apex_site_url(request).rstrip("/")
    if not apex or apex == origin:
        return response
    for prefix in (apex, f"http://{apex[8:]}" if apex.startswith("https://") else apex):
        if location == prefix or location.startswith(prefix + "/"):
            response.headers["Location"] = origin + location[len(prefix) :]
            break
    return response
