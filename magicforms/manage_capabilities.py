"""Studio route guards by entity permission (see ``entity_permissions``)."""

from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.utils.translation import gettext as _

from .entity_permissions import (
    ENTITY_PERMISSIONS,
    resolve_entity_id_from_form_pk,
    user_has_any_entity_permission,
    user_has_entity_permission,
)


def _studio_portal_can_access(user):
    from .entity_access import entity_ids_for_user

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return bool(entity_ids_for_user(user))


def studio_capability_required(
    *permissions: str,
    form_pk_kw: str | None = "pk",
    entity_pk_kw: str | None = None,
    any_entity: bool = False,
):
    """
    Require studio portal access plus at least one of ``permissions`` for the resolved entity.

    * ``entity_pk_kw`` — ``kwargs`` key is an entity primary key (e.g. email settings).
    * ``form_pk_kw`` — resolve entity via ``Form`` (default ``pk``).
    * ``any_entity`` — user needs the permission on any organization in scope.
    """
    perms = tuple(p for p in permissions if p in ENTITY_PERMISSIONS)
    if not perms:
        raise ValueError("studio_capability_required needs at least one permission")

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            u = request.user
            if not getattr(u, "is_authenticated", False) or not u.is_active:
                return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
            if not _studio_portal_can_access(u):
                return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)

            allowed = False
            if any_entity:
                allowed = user_has_any_entity_permission(u, *perms, request=request)
            elif entity_pk_kw and kwargs.get(entity_pk_kw) is not None:
                try:
                    eid = int(kwargs[entity_pk_kw])
                except (TypeError, ValueError):
                    eid = None
                if eid is not None:
                    allowed = user_has_entity_permission(u, eid, *perms, request=request)
            elif form_pk_kw and kwargs.get(form_pk_kw) is not None:
                eid = resolve_entity_id_from_form_pk(kwargs[form_pk_kw])
                if eid is not None:
                    allowed = user_has_entity_permission(u, eid, *perms, request=request)
            else:
                # List/global studio routes (e.g. responses grid) have no entity in the URL.
                allowed = user_has_any_entity_permission(u, *perms, request=request)

            if not allowed:
                messages.warning(
                    request,
                    _(
                        "You do not have permission for that area. "
                        "Ask an organization administrator if you need access."
                    ),
                )
                return redirect("manage:dashboard")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
