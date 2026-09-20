"""Column keys and projection for the studio responses grid."""

from __future__ import annotations

from typing import Any, Iterable

from django.db.models import CharField, F, OuterRef, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce, Concat, Lower, Trim
from django.utils.translation import gettext as _

from .dynamic_forms import field_collects_answer
from .models import FieldType, FormField, FormSubmission, SubmissionValue
from .responses_grid_applicant import applicant_meta_values
from .submission_responses_grid import display_submission_value

# Stable keys stored on saved views and passed in query strings.
META_COLUMNS: tuple[tuple[str, str], ...] = (
    ("meta:reference", "reference"),
    ("meta:applicant", "applicant"),
    ("meta:applicant_name", "applicant_name"),
    ("meta:submitted", "submitted"),
    ("meta:email", "email"),
    ("meta:account", "account"),
    ("meta:workflow", "workflow"),
    ("meta:step", "step"),
)

_META_FIELD_OFFSET = len(META_COLUMNS)

META_COLUMN_KEYS: tuple[str, ...] = tuple(k for k, _ in META_COLUMNS)
META_INDEX: dict[str, int] = {k: i for i, k in enumerate(META_COLUMN_KEYS)}

GRID_SORT_DEFAULT_KEY = "meta:submitted"
GRID_SORT_DEFAULT_DESC = True
RESPONSES_GRID_TABLE_ANCHOR = "mf-responses-grid-table"


def meta_column_label(key: str) -> str:
    labels = {
        "meta:reference": _("Reference"),
        "meta:applicant": _("Applicant"),
        "meta:applicant_name": _("Applicant name"),
        "meta:submitted": _("Submitted"),
        "meta:email": _("Email"),
        "meta:account": _("Account"),
        "meta:workflow": _("Workflow"),
        "meta:step": _("Step"),
    }
    return str(labels.get(key, key))


def field_column_key(field_pk: int) -> str:
    return f"field:{int(field_pk)}"


def _answer_fields(fields: Iterable[FormField]) -> list[FormField]:
    return [f for f in fields if field_collects_answer(f)]


def all_column_keys_for_form(fields: Iterable[FormField]) -> list[str]:
    return list(META_COLUMN_KEYS) + [field_column_key(f.pk) for f in _answer_fields(fields)]


def normalize_column_keys(requested: list[str] | None, fields: list[FormField]) -> list[str]:
    """Keep order; drop unknown keys; default to all columns when empty."""
    allowed = set(all_column_keys_for_form(fields))
    out: list[str] = []
    for key in requested or []:
        k = (key or "").strip()
        if k in allowed and k not in out:
            out.append(k)
    return out if out else all_column_keys_for_form(fields)


def parse_column_keys_param(raw: str | None, fields: list[FormField]) -> list[str]:
    if not (raw or "").strip():
        return []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return normalize_column_keys(parts, fields)


def column_catalog(fields: list[FormField]) -> list[dict[str, Any]]:
    """UI metadata: key, label, group ('meta' | 'field')."""
    items: list[dict[str, Any]] = [
        {"key": k, "label": meta_column_label(k), "group": "meta"} for k in META_COLUMN_KEYS
    ]
    for f in _answer_fields(fields):
        items.append(
            {
                "key": field_column_key(f.pk),
                "label": f.label,
                "group": "field",
                "field_pk": f.pk,
            }
        )
    return items


def parse_grid_sort(
    sort_param: str | None,
    order_param: str | None,
    column_keys: list[str],
) -> tuple[str, bool]:
    """Return ``(sort_column_key, descending)`` limited to visible columns."""
    keys = list(column_keys or [])
    allowed = set(keys)
    key = (sort_param or "").strip()
    if key in allowed:
        desc = (order_param or "asc").strip().lower() in ("desc", "descending")
        return key, desc
    if GRID_SORT_DEFAULT_KEY in allowed:
        return GRID_SORT_DEFAULT_KEY, GRID_SORT_DEFAULT_DESC
    if keys:
        return keys[0], False
    return GRID_SORT_DEFAULT_KEY, GRID_SORT_DEFAULT_DESC


def _grid_order(field: str, *, descending: bool):
    expr = F(field)
    return expr.desc(nulls_last=True) if descending else expr.asc(nulls_last=True)


def _annotate_name_sort(qs: QuerySet) -> QuerySet:
    return qs.annotate(
        _grid_sort=Lower(
            Trim(
                Coalesce(
                    Concat(
                        Coalesce("submitted_by__first_name", Value("")),
                        Value(" "),
                        Coalesce("submitted_by__last_name", Value("")),
                        output_field=CharField(),
                    ),
                    Value(""),
                    output_field=CharField(),
                )
            )
        )
    )


def _annotate_applicant_sort(qs: QuerySet) -> QuerySet:
    return qs.annotate(
        _grid_sort=Lower(
            Trim(
                Coalesce(
                    Concat(
                        Coalesce("submitted_by__first_name", Value("")),
                        Value(" "),
                        Coalesce("submitted_by__last_name", Value("")),
                        output_field=CharField(),
                    ),
                    "submitter_email",
                    "submitted_by__username",
                    Value(""),
                    output_field=CharField(),
                )
            )
        )
    )


def _annotate_email_sort(qs: QuerySet) -> QuerySet:
    return qs.annotate(
        _grid_sort=Lower(
            Coalesce(
                "submitter_email",
                "submitted_by__email",
                Value(""),
                output_field=CharField(),
            )
        )
    )


def apply_responses_grid_sort(
    qs: QuerySet,
    *,
    sort_key: str,
    descending: bool,
    fields: list[FormField],
) -> QuerySet:
    """Order submissions queryset for the active grid sort column."""
    if sort_key.startswith("field:"):
        field_pk = int(sort_key.split(":", 1)[1])
        if field_pk not in {f.pk for f in fields}:
            return qs.order_by("-submitted_at")
        subq = (
            SubmissionValue.objects.filter(
                submission_id=OuterRef("pk"),
                field_id=field_pk,
            )
            .order_by()
            .values("value")[:1]
        )
        return qs.annotate(_grid_sort=Subquery(subq, output_field=CharField())).order_by(
            _grid_order("_grid_sort", descending=descending)
        )

    if sort_key == "meta:reference":
        return qs.order_by(_grid_order("reference_token", descending=descending))
    if sort_key == "meta:submitted":
        return qs.order_by(_grid_order("submitted_at", descending=descending))
    if sort_key == "meta:workflow":
        return qs.order_by(_grid_order("workflow_state", descending=descending))
    if sort_key == "meta:step":
        return qs.order_by(_grid_order("current_step__label", descending=descending))
    if sort_key == "meta:account":
        return qs.order_by(_grid_order("submitted_by__username", descending=descending))
    if sort_key == "meta:email":
        return _annotate_email_sort(qs).order_by(_grid_order("_grid_sort", descending=descending))
    if sort_key == "meta:applicant_name":
        return _annotate_name_sort(qs).order_by(_grid_order("_grid_sort", descending=descending))
    if sort_key == "meta:applicant":
        return _annotate_applicant_sort(qs).order_by(_grid_order("_grid_sort", descending=descending))

    return qs.order_by("-submitted_at")


def headers_for_column_keys(column_keys: list[str], fields: list[FormField]) -> list[str]:
    field_by_pk = {f.pk: f for f in fields}
    headers: list[str] = []
    for key in column_keys:
        if key.startswith("meta:"):
            headers.append(meta_column_label(key))
        elif key.startswith("field:"):
            pk = int(key.split(":", 1)[1])
            f = field_by_pk.get(pk)
            headers.append(f.label if f else key)
    return headers


def _build_full_row(
    sub: FormSubmission,
    fields: list[FormField],
    by_field: dict[int, SubmissionValue],
) -> list[str]:
    from django.utils import timezone

    applicant = applicant_meta_values(sub)
    ref = str(sub.reference_token)
    ts = sub.submitted_at
    ts_s = timezone.localtime(ts).strftime("%Y-%m-%d %H:%M") if ts else ""
    wf = sub.get_workflow_state_display()
    step = sub.current_step.label if sub.current_step_id and sub.current_step else ""
    meta = [
        ref,
        applicant["applicant"],
        applicant["applicant_name"],
        ts_s,
        applicant["email"],
        applicant["account"],
        wf,
        step,
    ]
    field_cells = [display_submission_value(f, by_field.get(f.pk)) for f in fields]
    return meta + field_cells


def build_projected_grid_rows(
    submissions: Iterable[FormSubmission],
    fields: list[FormField],
    column_keys: list[str],
) -> tuple[list[str], list[list[str]]]:
    """
    Return ``(headers, data_rows)`` for the given visible ``column_keys``.
    """
    keys = normalize_column_keys(column_keys, fields)
    headers = headers_for_column_keys(keys, fields)
    field_order = [f.pk for f in fields]
    rows: list[list[str]] = []
    for sub in submissions:
        by_field = {v.field_id: v for v in sub.values.all()}
        full = _build_full_row(sub, fields, by_field)
        row: list[str] = []
        for key in keys:
            if key.startswith("meta:"):
                row.append(full[META_INDEX[key]])
            else:
                pk = int(key.split(":", 1)[1])
                row.append(full[_META_FIELD_OFFSET + field_order.index(pk)])
        rows.append(row)
    return headers, rows


def response_cards_from_rows(
    headers: list[str],
    data_rows: list[list[str]],
    *,
    column_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    keys = column_keys or []
    ref_i = keys.index("meta:reference") if "meta:reference" in keys else 0
    applicant_i = keys.index("meta:applicant") if "meta:applicant" in keys else None
    submitted_i = keys.index("meta:submitted") if "meta:submitted" in keys else None
    skip_in_pairs = {"meta:reference", "meta:applicant", "meta:submitted"}

    cards: list[dict[str, Any]] = []
    for row in data_rows:
        if not row:
            continue
        ref = row[ref_i] if ref_i < len(row) else ""
        applicant = (
            row[applicant_i]
            if applicant_i is not None and applicant_i < len(row)
            else ""
        )
        meta_line = (
            row[submitted_i]
            if submitted_i is not None and submitted_i < len(row)
            else (row[1] if len(row) > 1 else "")
        )
        pairs = [
            (h, v)
            for k, h, v in zip(keys, headers, row, strict=True)
            if k not in skip_in_pairs
        ] if keys else list(zip(headers, row, strict=True))[1:]
        cards.append(
            {
                "reference": ref,
                "applicant": applicant,
                "meta_line": meta_line,
                "pairs": pairs,
            }
        )
    return cards
