"""Saved responses-grid view templates (columns + sharing)."""

from __future__ import annotations

from .opaque_ids import parse_id as oid_parse
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, QuerySet

from .entity_access import _staff_users_for_entities_qs, effective_entity_ids
from .models import Form, ResponsesGridView, ResponsesGridViewShare
from .responses_grid_columns import all_column_keys_for_form, normalize_column_keys

User = get_user_model()


def responses_grid_views_for_form(user, form: Form) -> QuerySet:
    """Owned or shared views for this form, ordered for display."""
    return (
        ResponsesGridView.objects.filter(form=form)
        .filter(Q(owner=user) | Q(shares__user=user))
        .select_related("owner")
        .prefetch_related("shares__user")
        .distinct()
        .order_by("name")
    )


def user_may_access_grid_view(user, view: ResponsesGridView) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if view.owner_id == user.pk:
        return True
    return ResponsesGridViewShare.objects.filter(view=view, user=user).exists()


def user_owns_grid_view(user, view: ResponsesGridView) -> bool:
    return bool(getattr(user, "is_authenticated", False) and view.owner_id == user.pk)


def default_grid_view_for_user(user, form: Form) -> ResponsesGridView | None:
    owned = ResponsesGridView.objects.filter(form=form, owner=user, is_default=True).first()
    if owned:
        return owned
    return (
        ResponsesGridView.objects.filter(form=form, owner=user, is_default=False)
        .order_by("name")
        .first()
    )


def resolve_active_column_keys(
    user,
    form: Form,
    fields: list,
    *,
    view_pk: str | None,
    cols_param: str | None,
) -> tuple[list[str], ResponsesGridView | None]:
    """
    Pick visible columns from explicit view id, ``cols`` query param, user's default
    saved view, or all columns.
    """
    view: ResponsesGridView | None = None
    if view_pk and oid_parse(view_pk):
        candidate = (
            ResponsesGridView.objects.filter(form=form, pk=oid_parse(view_pk))
            .select_related("owner", "form")
            .first()
        )
        if candidate and user_may_access_grid_view(user, candidate):
            view = candidate
            return normalize_column_keys(list(candidate.column_keys or []), fields), view

    parsed = normalize_column_keys(
        [p.strip() for p in (cols_param or "").split(",") if p.strip()],
        fields,
    )
    if cols_param and (cols_param or "").strip():
        all_keys = all_column_keys_for_form(fields)
        if parsed != all_keys:
            return parsed, None

    default_v = default_grid_view_for_user(user, form)
    if default_v and user_may_access_grid_view(user, default_v):
        return normalize_column_keys(list(default_v.column_keys or []), fields), default_v

    return all_column_keys_for_form(fields), None


@transaction.atomic
def save_responses_grid_view(
    user,
    form: Form,
    *,
    name: str,
    column_keys: list[str],
    fields: list,
    view_id: int | None = None,
    set_default: bool = False,
) -> ResponsesGridView:
    name = (name or "").strip()[: ResponsesGridView.MAX_NAME_LEN]
    if not name:
        raise ValueError("name required")
    keys = normalize_column_keys(column_keys, fields)

    if view_id:
        view = ResponsesGridView.objects.select_for_update().get(pk=view_id, form=form, owner=user)
        view.name = name
        view.column_keys = keys
        view.save(update_fields=["name", "column_keys", "updated_at"])
    else:
        view = ResponsesGridView.objects.create(
            form=form,
            owner=user,
            name=name,
            column_keys=keys,
            is_default=set_default,
        )

    if set_default:
        ResponsesGridView.objects.filter(form=form, owner=user).exclude(pk=view.pk).update(
            is_default=False
        )
        if not view.is_default:
            view.is_default = True
            view.save(update_fields=["is_default", "updated_at"])
    return view


def delete_responses_grid_view(user, view: ResponsesGridView) -> None:
    if not user_owns_grid_view(user, view):
        raise PermissionError
    view.delete()


def owned_grid_views_for_user(user, saved_views: list[ResponsesGridView]) -> list[ResponsesGridView]:
    return [v for v in saved_views if v.owner_id == user.pk]


def resolve_share_grid_view(
    user,
    saved_views: list[ResponsesGridView],
    *,
    active_view: ResponsesGridView | None,
    share_view_pk: str | None = None,
) -> ResponsesGridView | None:
    """View whose sharing settings are edited in the UI (active if owned, else picked/first owned)."""
    owned = owned_grid_views_for_user(user, saved_views)
    if not owned:
        return None
    if active_view is not None and user_owns_grid_view(user, active_view):
        return active_view
    if share_view_pk and oid_parse(share_view_pk):
        pk = oid_parse(share_view_pk)
        for v in owned:
            if v.pk == pk:
                return v
    return owned[0]


def share_targets_queryset(owner, form: Form, q: str = ""):
    """Staff in the form's entity (or superuser scope) eligible to receive a shared view."""
    return (
        _staff_users_for_entities_qs(owner, q, request=None)
        .filter(entity_memberships__entity_id=form.entity_id)
        .distinct()
    )


@transaction.atomic
def set_view_shares(
    owner,
    view: ResponsesGridView,
    *,
    user_ids: list[int],
) -> list[ResponsesGridViewShare]:
    if not user_owns_grid_view(owner, view):
        raise PermissionError
    allowed = set(
        share_targets_queryset(owner, view.form)
        .filter(pk__in=user_ids)
        .exclude(pk=owner.pk)
        .values_list("pk", flat=True)
    )
    ResponsesGridViewShare.objects.filter(view=view).exclude(user_id__in=allowed).delete()
    existing = set(
        ResponsesGridViewShare.objects.filter(view=view).values_list("user_id", flat=True)
    )
    created: list[ResponsesGridViewShare] = []
    for uid in allowed:
        if uid in existing:
            continue
        created.append(
            ResponsesGridViewShare.objects.create(
                view=view,
                user_id=uid,
                shared_by=owner,
            )
        )
    return created
