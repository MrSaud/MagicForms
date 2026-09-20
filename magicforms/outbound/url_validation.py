"""SSRF-safe outbound URL checks."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_outbound_endpoint_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValidationError("Endpoint URL is required when the integration is active.")
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValidationError("Use a full URL starting with https:// or http://.")
    if not settings.DEBUG and parsed.scheme != "https":
        raise ValidationError("Production outbound endpoints must use https://.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValidationError("Endpoint URL must include a hostname.")
    if host in ("localhost", "127.0.0.1", "::1"):
        if not settings.DEBUG:
            raise ValidationError("localhost endpoints are only allowed in DEBUG mode.")
        return url
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValidationError(f"Could not resolve hostname: {host}") from exc
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValidationError(
                "Endpoint hostname resolves to a private or reserved address."
            )
    return url
