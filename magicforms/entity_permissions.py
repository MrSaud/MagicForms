"""
Per-organization studio permissions on ``EntityMembership``.

Each capability area has **read** (view/list) and **write** (create, edit, delete, export).
Staff and superusers bypass flags. Only staff or superusers may grant permissions.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

# Capability area prefixes (field names are ``{area}_read`` / ``{area}_write``).
MANAGE_PEOPLE = "manage_people"
MANAGE_FORMS = "manage_forms"
VIEW_RESPONSES = "view_responses"
EXPORT_RESPONSES = "export_responses"
MANAGE_DELEGATIONS = "manage_delegations"
MANAGE_CATEGORIES = "manage_categories"
MANAGE_ENTITY_SETTINGS = "manage_entity_settings"

PERMISSION_AREAS: tuple[tuple[str, str], ...] = (
    (MANAGE_PEOPLE, _("People")),
    (MANAGE_FORMS, _("Forms & builder")),
    (VIEW_RESPONSES, _("Responses")),
    (EXPORT_RESPONSES, _("Export responses")),
    (MANAGE_DELEGATIONS, _("Delegations")),
    (MANAGE_CATEGORIES, _("Categories")),
    (MANAGE_ENTITY_SETTINGS, _("Organization settings")),
)

READ_SUFFIX = "_read"
WRITE_SUFFIX = "_write"


def permission_field(area: str, *, write: bool = False) -> str:
    return f"{area}{WRITE_SUFFIX if write else READ_SUFFIX}"


def permission_fields_for_area(area: str) -> tuple[str, str]:
    return permission_field(area, write=False), permission_field(area, write=True)


ENTITY_PERMISSIONS: tuple[str, ...] = tuple(
    field
    for area, _label in PERMISSION_AREAS
    for field in permission_fields_for_area(area)
)

# Convenience constants for route guards
MANAGE_PEOPLE_READ = permission_field(MANAGE_PEOPLE)
MANAGE_PEOPLE_WRITE = permission_field(MANAGE_PEOPLE, write=True)
MANAGE_FORMS_READ = permission_field(MANAGE_FORMS)
MANAGE_FORMS_WRITE = permission_field(MANAGE_FORMS, write=True)
VIEW_RESPONSES_READ = permission_field(VIEW_RESPONSES)
VIEW_RESPONSES_WRITE = permission_field(VIEW_RESPONSES, write=True)
EXPORT_RESPONSES_READ = permission_field(EXPORT_RESPONSES)
EXPORT_RESPONSES_WRITE = permission_field(EXPORT_RESPONSES, write=True)
MANAGE_DELEGATIONS_READ = permission_field(MANAGE_DELEGATIONS)
MANAGE_DELEGATIONS_WRITE = permission_field(MANAGE_DELEGATIONS, write=True)
MANAGE_CATEGORIES_READ = permission_field(MANAGE_CATEGORIES)
MANAGE_CATEGORIES_WRITE = permission_field(MANAGE_CATEGORIES, write=True)
MANAGE_ENTITY_SETTINGS_READ = permission_field(MANAGE_ENTITY_SETTINGS)
MANAGE_ENTITY_SETTINGS_WRITE = permission_field(MANAGE_ENTITY_SETTINGS, write=True)


def read_or_write(area: str) -> tuple[str, str]:
    """Pass to ``studio_capability_required`` for view/list routes (read or write suffices)."""
    return permission_fields_for_area(area)


def studio_staff_bypass(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_active
        and (getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))
    )


def can_grant_entity_permissions(user) -> bool:
    return studio_staff_bypass(user)


def _expand_permissions_for_check(permissions: tuple[str, ...]) -> set[str]:
    """Granting write also satisfies read checks."""
    expanded: set[str] = set()
    for perm in permissions:
        if perm not in ENTITY_PERMISSIONS:
            continue
        expanded.add(perm)
        if perm.endswith(READ_SUFFIX):
            expanded.add(perm[: -len(READ_SUFFIX)] + WRITE_SUFFIX)
    return expanded


def _perm_q(*permissions: str) -> Q:
    expanded = _expand_permissions_for_check(tuple(permissions))
    q = Q()
    for perm in expanded:
        q |= Q(**{perm: True})
    return q


def user_has_entity_permission(user, entity_id: int, *permissions: str, request=None) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if studio_staff_bypass(user):
        return True
    if not permissions:
        return False
    from .entity_access import user_may_access_entity
    from .models import EntityMembership

    if not user_may_access_entity(user, entity_id, request=request):
        return False
    return EntityMembership.objects.filter(
        user=user,
        entity_id=entity_id,
    ).filter(_perm_q(*permissions)).exists()


def user_has_any_entity_permission(user, *permissions: str, request=None) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if studio_staff_bypass(user):
        return True
    if not permissions:
        return False
    from .entity_access import effective_entity_ids
    from .models import EntityMembership

    qs = EntityMembership.objects.filter(user=user).filter(_perm_q(*permissions))
    ids = effective_entity_ids(user, request)
    if ids is not None:
        qs = qs.filter(entity_id__in=ids)
    return qs.exists()


def user_has_entity_read(user, entity_id: int, area: str, request=None) -> bool:
    read_f, write_f = permission_fields_for_area(area)
    return user_has_entity_permission(user, entity_id, read_f, write_f, request=request)


def user_has_entity_write(user, entity_id: int, area: str, request=None) -> bool:
    return user_has_entity_permission(
        user,
        entity_id,
        permission_field(area, write=True),
        request=request,
    )


def user_has_any_entity_read(user, area: str, request=None) -> bool:
    return user_has_any_entity_permission(user, *read_or_write(area), request=request)


def user_has_any_entity_write(user, area: str, request=None) -> bool:
    return user_has_any_entity_permission(
        user,
        permission_field(area, write=True),
        request=request,
    )


def entities_with_permission(user, *permissions: str, request=None) -> list[int]:
    if studio_staff_bypass(user):
        from .entity_access import effective_entity_ids

        ids = effective_entity_ids(user, request)
        if ids is None:
            from .models import Entity

            return list(Entity.objects.values_list("pk", flat=True))
        return list(ids)
    from .entity_access import effective_entity_ids
    from .models import EntityMembership

    qs = EntityMembership.objects.filter(user=user).filter(_perm_q(*permissions))
    ids = effective_entity_ids(user, request)
    if ids is not None:
        qs = qs.filter(entity_id__in=ids)
    return list(qs.values_list("entity_id", flat=True).distinct())


def resolve_entity_id_from_form_pk(form_pk: int | str | None) -> int | None:
    if form_pk is None:
        return None
    try:
        pk = int(form_pk)
    except (TypeError, ValueError):
        return None
    from .models import Form

    return Form.objects.filter(pk=pk).values_list("entity_id", flat=True).first()


def membership_permissions_for_user(user) -> dict[int, dict[str, bool]]:
    from .models import EntityMembership

    out: dict[int, dict[str, bool]] = {}
    for row in EntityMembership.objects.filter(user=user):
        out[row.entity_id] = {perm: bool(getattr(row, perm, False)) for perm in ENTITY_PERMISSIONS}
    return out


def permission_groups_for_entity(
    entity_id: int,
    perm_map: dict[int, dict[str, bool]],
) -> list[dict]:
    """Template rows: area label plus read/write checkbox metadata."""
    ent_perms = perm_map.get(entity_id, {})
    groups = []
    for area, label in PERMISSION_AREAS:
        read_f, write_f = permission_fields_for_area(area)
        groups.append(
            {
                "area": area,
                "label": label,
                "read": {
                    "field": read_f,
                    "input_name": f"membership_{entity_id}_{read_f}",
                    "checked": ent_perms.get(read_f, False),
                },
                "write": {
                    "field": write_f,
                    "input_name": f"membership_{entity_id}_{write_f}",
                    "checked": ent_perms.get(write_f, False),
                },
            }
        )
    return groups


def apply_membership_permissions_from_post(
    editor,
    target_user,
    post,
    *,
    allowed_entity_ids: set[int],
) -> None:
    """Persist membership rows and permission flags (staff/superuser grant only)."""
    from .models import EntityMembership

    if not can_grant_entity_permissions(editor):
        return
    raw_ids = [int(x) for x in post.getlist("entity_ids") if str(x).isdigit()]
    entity_ids = [eid for eid in raw_ids if eid in allowed_entity_ids]
    EntityMembership.objects.filter(
        user=target_user,
        entity_id__in=allowed_entity_ids,
    ).exclude(entity_id__in=entity_ids).delete()
    for eid in entity_ids:
        membership, _ = EntityMembership.objects.get_or_create(user=target_user, entity_id=eid)
        for perm in ENTITY_PERMISSIONS:
            key = f"membership_{eid}_{perm}"
            setattr(membership, perm, key in post)
        membership.save(update_fields=[*ENTITY_PERMISSIONS])


def people_assignable_entities(editor, request=None):
    """Organizations the editor may attach on People create/edit (studio scope only)."""
    from .entity_access import entities_queryset_for_user

    qs = entities_queryset_for_user(editor, request)
    if studio_staff_bypass(editor):
        return qs
    eids = entities_with_permission(editor, *read_or_write(MANAGE_PEOPLE), request=request)
    return qs.filter(pk__in=eids)


def people_allowed_entity_ids(editor, request=None) -> set[int]:
    return set(people_assignable_entities(editor, request).values_list("pk", flat=True))
