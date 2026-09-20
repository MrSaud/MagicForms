"""Activate Django locale for mobile API requests (form labels, errors)."""

from __future__ import annotations

from django.utils import translation


def mobile_language_code(request) -> str:
    """Resolve ``en`` or ``ar`` from ``Accept-Language`` or ``?lang=``."""
    accept = (request.headers.get("Accept-Language") or "").strip().lower()
    if accept:
        primary = accept.split(",")[0].strip().split(";")[0].strip()
        if primary.startswith("ar") or primary == "ar":
            return "ar"
        if primary.startswith("en") or primary == "en":
            return "en"
    q = (request.GET.get("lang") or "").strip().lower()
    if q in ("ar", "en"):
        return q
    return "en"


def mobile_locale_context(request):
    """Context manager: activate request language for the view body."""
    return translation.override(mobile_language_code(request))
