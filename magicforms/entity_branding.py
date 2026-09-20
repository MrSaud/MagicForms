"""Organization logo URLs for web banners and mobile apps."""

from __future__ import annotations

from django.http import HttpRequest

from magicforms.models import Entity


def entity_logo_url(entity: Entity | None, request: HttpRequest | None = None) -> str:
    if not entity or not getattr(entity, "page_logo", None) or not entity.page_logo:
        return ""
    try:
        url = entity.page_logo.url
    except (ValueError, AttributeError):
        return ""
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def entities_for_mobile_user_payload(user, request: HttpRequest | None = None) -> list[dict]:
    from magicforms.entity_access import entity_ids_for_user
    from magicforms.models import Entity

    ids = entity_ids_for_user(user)
    if ids == []:
        return []
    qs = Entity.objects.filter(is_active=True).order_by("name")
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    out = []
    for e in qs:
        row = {"id": e.pk, "slug": e.slug, "name": e.name}
        logo = entity_logo_url(e, request)
        if logo:
            row["logo_url"] = logo
        out.append(row)
    return out


def mobile_banner_branding(user, request: HttpRequest) -> dict:
    """Primary banner logo for native apps (single org with logo, else empty)."""
    entities = entities_for_mobile_user_payload(user, request)
    if len(entities) == 1:
        ent = entities[0]
        return {
            "banner_logo_url": ent.get("logo_url") or "",
            "banner_entity_name": ent.get("name") or "",
        }
    return {"banner_logo_url": "", "banner_entity_name": ""}


def resolve_manage_banner_entity(request, form_obj=None) -> Entity | None:
    if form_obj is not None and getattr(form_obj, "entity", None):
        return form_obj.entity
    portal = getattr(request, "portal_entity", None)
    if portal is not None:
        return portal
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None
    from magicforms.entity_access import entities_queryset_for_user

    ents = list(entities_queryset_for_user(user, request))
    if len(ents) == 1:
        return ents[0]
    return None
