"""
Multi-entity access: studio data is scoped by ``EntityMembership``.

* **Superusers**: ``entity_ids_for_user`` returns ``None`` (no membership filter — conceptually “all”).
  In request-bound studio code, ``effective_entity_ids(user, request)`` applies an optional session
  subset so super admins can focus on selected organizations.
* **Staff and non-staff members**: returns the list of entity PKs they belong to; empty means the user
  has no organization-linked studio portal (they still use public routes as normal users).
* **Portal vs capabilities**: ``/manage/`` home, inbox, and submission search are available to any
  member with at least one entity. Builder, responses, exports, and org admin require the matching
  flags on ``EntityMembership`` (staff/superuser bypass flags).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q, QuerySet

# Session value ``"all"``, a single entity PK (int), or legacy list of one PK — superusers only (see ``effective_entity_ids``).
MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY = "manage_superuser_entity_scope"


def entity_ids_for_user(user) -> list[int] | None:
    """
    Entity primary keys the user belongs to, or ``None`` if the user is a superuser
    (all entities). Members with no rows get an empty list.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return []
    if user.is_superuser:
        return None
    from .models import EntityMembership

    return list(EntityMembership.objects.filter(user=user).values_list("entity_id", flat=True))


def effective_entity_ids(user, request=None) -> list[int] | None:
    """
    Entity IDs used for studio queries. Same as ``entity_ids_for_user`` for non-superusers (any member
    with entity rows); for superusers, honors ``request.session[MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY]``:

    * missing / ``\"all\"`` → ``None`` (no filter — all organizations)
    * single entity PK (``int`` or legacy one-item ``list``) → restrict to that organization
    """
    ids = entity_ids_for_user(user)
    if ids is not None:
        return ids
    if not getattr(user, "is_superuser", False):
        return ids
    if request is None:
        return None
    from .models import Entity

    scope = request.session.get(MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY, "all")
    if scope == "all" or scope is None:
        return None
    if isinstance(scope, int):
        valid = list(Entity.objects.filter(pk=scope).values_list("pk", flat=True))
        return valid if valid else None
    if isinstance(scope, list):
        raw = [int(x) for x in scope if str(x).isdigit()]
        if not raw:
            return None
        valid = list(Entity.objects.filter(pk=raw[0]).values_list("pk", flat=True))
        return valid if valid else None
    return None


def forms_queryset_for_user(
    user, *, visibility: str = "active", request=None, for_lists: bool = False
) -> QuerySet:
    """
    Return forms scoped to ``user``.

    ``visibility``:
      * ``"active"`` (default): not soft-deleted.
      * ``"deleted"``: soft-deleted only (archived).
      * ``"all"``: active and archived (typically with super admin manage views).

    When ``for_lists`` is True, forms with ``hide_from_form_lists`` are excluded (studio home and similar
    listings). Detail views and manage operations pass ``for_lists=False`` (default).
    """
    from .models import Form

    ids = effective_entity_ids(user, request)
    if ids is None:
        qs = Form.objects.all()
    elif not ids:
        return Form.objects.none()
    else:
        qs = Form.objects.filter(entity_id__in=ids)

    if visibility == "active":
        qs = qs.filter(deleted_at__isnull=True)
    elif visibility == "deleted":
        qs = qs.filter(deleted_at__isnull=False)
    elif visibility != "all":
        raise ValueError(f"Unknown forms visibility: {visibility!r}")
    if for_lists:
        qs = qs.filter(hide_from_form_lists=False)
    return qs


def categories_queryset_for_user(user, request=None) -> QuerySet:
    from .models import FormCategory

    ids = effective_entity_ids(user, request)
    if ids is None:
        return FormCategory.objects.all()
    if not ids:
        return FormCategory.objects.none()
    return FormCategory.objects.filter(entity_id__in=ids)


def entities_queryset_for_user(user, request=None) -> QuerySet:
    from .models import Entity

    ids = effective_entity_ids(user, request)
    if ids is None:
        return Entity.objects.all().order_by("name")
    if not ids:
        return Entity.objects.none()
    return Entity.objects.filter(pk__in=ids).order_by("name")


def delegations_queryset_for_user(user, request=None) -> QuerySet:
    from .models import WorkflowDelegation

    ids = effective_entity_ids(user, request)
    if ids is None:
        return WorkflowDelegation.objects.all()
    if not ids:
        return WorkflowDelegation.objects.none()
    return WorkflowDelegation.objects.filter(entity_id__in=ids)


def user_may_access_entity(user, entity_id: int, request=None) -> bool:
    ids = effective_entity_ids(user, request)
    if ids is None:
        return True
    return entity_id in ids


def users_visible_in_people(user, request=None) -> QuerySet:
    """
    Users listed on /manage/people/: organization members in the editor's scope.

    Superusers see every account (optionally narrowed by session scope). Staff see members of their
    organizations. Non-staff editors only see users in organizations where they have ``manage_people``.
    """
    User = get_user_model()
    from .entity_permissions import entities_with_permission, studio_staff_bypass

    if studio_staff_bypass(user):
        ids = effective_entity_ids(user, request)
        if ids is None:
            return User.objects.all().order_by("username")
        if not ids:
            return User.objects.none()
    else:
        from .entity_permissions import MANAGE_PEOPLE, read_or_write

        ids = entities_with_permission(user, *read_or_write(MANAGE_PEOPLE), request=request)
        if not ids:
            return User.objects.none()
    from .models import EntityMembership

    uids = EntityMembership.objects.filter(entity_id__in=ids).values_list("user_id", flat=True).distinct()
    return User.objects.filter(pk__in=uids).order_by("username")


def _entity_users_for_entities_qs(user, q: str = "", request=None) -> QuerySet:
    """
    Active organization members in the viewer's entity scope (staff and non-staff).
    Superusers without a session scope see all active users; with scope, same as org staff.
    """
    User = get_user_model()
    ids = effective_entity_ids(user, request)
    if ids is None:
        qs = User.objects.filter(is_active=True)
    elif not ids:
        return User.objects.none()
    else:
        from .models import EntityMembership

        uids = EntityMembership.objects.filter(entity_id__in=ids).values_list("user_id", flat=True).distinct()
        qs = User.objects.filter(pk__in=uids, is_active=True)
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(profile__job_title__icontains=q)
            | Q(profile__department__icontains=q)
        )
    return qs.order_by("username")


def entity_users_for_entities_search(user, q: str, request=None) -> QuerySet:
    """JSON user search: organization members (staff and end users), matched by name or job title, capped at 50."""
    return _entity_users_for_entities_qs(user, q, request=request).select_related("profile")[:50]


def staff_users_for_entity(entity_id: int) -> QuerySet:
    """Active staff assignees belonging to a given entity (for workflow step pickers)."""
    User = get_user_model()
    from .models import EntityMembership

    uids = EntityMembership.objects.filter(entity_id=entity_id).values_list("user_id", flat=True)
    return User.objects.filter(pk__in=uids, is_active=True, is_staff=True).order_by("username")


def entity_users_for_entity(entity_id: int) -> QuerySet:
    """Active organization members (staff and non-staff) for workflow assignee pickers."""
    User = get_user_model()
    from .models import EntityMembership

    uids = EntityMembership.objects.filter(entity_id=entity_id).values_list("user_id", flat=True)
    return User.objects.filter(pk__in=uids, is_active=True).order_by("username")


def entity_users_for_entity_search(entity_id: int, q: str = "") -> QuerySet:
    """Searchable subset of :func:`entity_users_for_entity` (caller may slice), matched by name or job title."""
    qs = entity_users_for_entity(entity_id)
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(profile__job_title__icontains=q)
            | Q(profile__department__icontains=q)
        )
    return qs.select_related("profile").order_by("username")


def _staff_users_for_entities_qs(user, q: str = "", request=None) -> QuerySet:
    """
    Unsliced staff-user queryset for entity scope (and optional search ``q``).
    Callers that need a cap should slice after any further filters.
    """
    User = get_user_model()
    ids = effective_entity_ids(user, request)
    if ids is None:
        qs = User.objects.filter(is_active=True, is_staff=True)
    elif not ids:
        return User.objects.none()
    else:
        from .models import EntityMembership

        uids = EntityMembership.objects.filter(entity_id__in=ids).values_list("user_id", flat=True).distinct()
        qs = User.objects.filter(pk__in=uids, is_active=True, is_staff=True)
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )
    return qs.order_by("username")


def staff_users_for_entities_search(user, q: str, request=None) -> QuerySet:
    """
    Staff users for the JSON assignee search: same entity as ``user`` (or all for superuser),
    filtered by optional search string ``q``. Limited to 50 results.
    """
    return _staff_users_for_entities_qs(user, q, request=request)[:50]


def published_forms_for_public_home(user) -> QuerySet:
    """
    Published forms shown on the public home page: superuser sees all published;
    authenticated users see published forms in their entities; anonymous visitors see only
    forms that allow access without signing in.

    Draft forms are never included (``is_published=True`` only).
    """
    from django.utils import timezone

    from .models import Form

    today = timezone.localdate()
    base = (
        Form.objects.filter(is_published=True, deleted_at__isnull=True, hide_from_form_lists=False)
        .filter(Q(submission_deadline__isnull=True) | Q(submission_deadline__gte=today))
        .select_related("category", "entity")
        .order_by("entity__name", "title")
    )
    if not getattr(user, "is_authenticated", False):
        return base.filter(is_for_public=True)
    ids = entity_ids_for_user(user)
    if ids is None:
        return base
    if not ids:
        return Form.objects.none()
    return base.filter(entity_id__in=ids)


def entities_for_public_directory():
    """Active organizations that opt in to the global home directory."""
    from .models import Entity

    return Entity.objects.filter(is_active=True, show_on_public_directory=True).order_by("name")


def published_forms_for_entity_portal(entity, request=None):
    """Published forms for a single organization’s public portal."""
    from django.utils import timezone

    from .models import Form, WorkflowStep

    if not entity.is_active:
        return Form.objects.none()
    today = timezone.localdate()
    qs = (
        Form.objects.filter(
            entity=entity,
            is_published=True,
            deleted_at__isnull=True,
            hide_from_form_lists=False,
        )
        .filter(Q(submission_deadline__isnull=True) | Q(submission_deadline__gte=today))
        .select_related("category", "entity")
        .prefetch_related(
            Prefetch(
                "workflow_steps",
                queryset=WorkflowStep.objects.order_by("order", "id"),
            )
        )
        .order_by("title")
    )
    user = getattr(request, "user", None) if request is not None else None
    if not (user and getattr(user, "is_authenticated", False)):
        qs = qs.filter(is_for_public=True)
    return qs
