"""Generate unique URL-safe slugs and internal field names (studio auto-fill)."""

from __future__ import annotations

from django.db.models import QuerySet
from django.utils.text import slugify


def unique_slug_within(
    queryset: QuerySet,
    base: str,
    *,
    slug_field: str = "slug",
    exclude_pk: int | None = None,
    max_length: int = 80,
    fallback: str = "item",
) -> str:
    """Return ``base`` slugified, unique within ``queryset`` (adds ``-2``, ``-3``, …)."""
    root = slugify(base)[:max_length].strip("-") or fallback
    slug = root
    n = 2
    while True:
        qs = queryset.filter(**{slug_field: slug})
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        if not qs.exists():
            return slug
        suffix = f"-{n}"
        slug = f"{root[: max_length - len(suffix)]}{suffix}"
        n += 1


def unique_form_slug(title: str, entity, *, exclude_pk: int | None = None) -> str:
    from .models import Form

    base = (title or "").strip() or "form"
    return unique_slug_within(
        Form.objects.filter(entity_id=entity.pk),
        base,
        exclude_pk=exclude_pk,
        max_length=120,
        fallback="form",
    )


def unique_form_field_name(label: str, form, *, exclude_pk: int | None = None) -> str:
    from .models import FormField

    base = (label or "").strip() or "field"
    return unique_slug_within(
        FormField.objects.filter(form_id=form.pk),
        base,
        slug_field="name",
        exclude_pk=exclude_pk,
        max_length=80,
        fallback="field",
    )


def unique_workflow_step_slug(label: str, form, *, exclude_pk: int | None = None) -> str:
    from .models import WorkflowStep

    base = (label or "").strip() or "step"
    return unique_slug_within(
        WorkflowStep.objects.filter(form_id=form.pk),
        base,
        exclude_pk=exclude_pk,
        max_length=80,
        fallback="step",
    )
