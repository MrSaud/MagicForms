"""Decorators for mobile API views."""

from __future__ import annotations

import functools

from django.http import JsonResponse

from magicforms.api.locale import mobile_locale_context
from magicforms.mobile_auth import bearer_token_from_request, user_from_mobile_token


def mobile_api_errors(view_func):
    """Return JSON errors for unexpected failures."""

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        with mobile_locale_context(request):
            try:
                return view_func(request, *args, **kwargs)
            except Exception:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "server_error",
                        "message": "An unexpected error occurred.",
                    },
                    status=500,
                )

    return wrapper


def mobile_token_required(view_func):
    """Require ``Authorization: Bearer <token>``; sets ``request.mobile_user``."""

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = user_from_mobile_token(bearer_token_from_request(request))
        if user is None:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "authentication_required",
                    "message": "Invalid or expired token. Sign in again.",
                },
                status=401,
            )
        request.mobile_user = user
        return view_func(request, *args, **kwargs)

    return wrapper
