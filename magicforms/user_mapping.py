"""Resolve FormField.mapping_key values from the signed-in user (and optional profile)."""

from datetime import datetime

from .models import FieldType


def _user_builtin(user, key_lower: str):
    if key_lower in ("email",):
        return (getattr(user, "email", None) or "").strip()
    if key_lower in ("username", "user_name"):
        return (getattr(user, "username", None) or "").strip()
    if key_lower in ("first_name", "firstname"):
        return (getattr(user, "first_name", None) or "").strip()
    if key_lower in ("last_name", "lastname"):
        return (getattr(user, "last_name", None) or "").strip()
    if key_lower in ("full_name", "name", "display_name"):
        if hasattr(user, "get_full_name"):
            return (user.get_full_name() or "").strip()
        parts = [
            getattr(user, "first_name", None) or "",
            getattr(user, "last_name", None) or "",
        ]
        return " ".join(p for p in parts if p).strip()
    return None


def resolve_mapping_raw(user, key: str) -> str | None:
    """
    Return a string value from user/profile for key, or None if not found / not authenticated.
    Key is case-insensitive; hyphens map to underscores for lookups.
    """
    if not user.is_authenticated:
        return None
    key = (key or "").strip()
    if not key:
        return None

    key_lower = key.lower().replace("-", "_")
    builtin = _user_builtin(user, key_lower)
    if builtin is not None:
        return builtin or None

    candidates = [
        key,
        key_lower,
        key.replace("-", "_"),
    ]

    for attr in candidates:
        if hasattr(user, attr):
            v = getattr(user, attr)
            if callable(v):
                continue
            if v is not None and v != "":
                return str(v).strip()

    profile = getattr(user, "profile", None)
    if profile is not None:
        for attr in candidates:
            if hasattr(profile, attr):
                v = getattr(profile, attr)
                if callable(v):
                    continue
                if v is not None and v != "":
                    return str(v).strip()

    return None


def _coerce_for_field(ff, raw: str):
    if raw is None or raw == "":
        return None
    if ff.field_type == FieldType.CHECKBOX:
        return raw.lower() in ("1", "true", "yes", "on", "y")
    if ff.field_type == FieldType.NUMBER:
        from decimal import Decimal

        try:
            return Decimal(raw.replace(",", "."))
        except Exception:
            return None
    if ff.field_type == FieldType.DATE:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw[:10], fmt).date()
            except ValueError:
                continue
        return None
    if ff.field_type == FieldType.CHECKLIST:
        choices = set(ff.choice_list())
        parts = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if not parts:
            parts = [p.strip() for p in raw.split(",") if p.strip()]
        picked = [p for p in parts if p in choices]
        return picked if picked else None
    if ff.field_type in (FieldType.SELECT, FieldType.RADIO):
        choices = ff.choice_list()
        if raw in choices:
            return raw
        return None
    return raw


def build_initial_from_mappings(request, fields_def) -> dict:
    """Initial dict for DynamicPublicForm: keys f_<pk>."""
    if not request.user.is_authenticated:
        return {}

    initial = {}
    for ff in fields_def:
        if ff.field_type == FieldType.FILE:
            continue
        mk = (getattr(ff, "mapping_key", None) or "").strip()
        if not mk:
            continue
        raw = resolve_mapping_raw(request.user, mk)
        if raw is None:
            continue
        coerced = _coerce_for_field(ff, raw)
        if coerced is None and ff.field_type in (
            FieldType.NUMBER,
            FieldType.DATE,
            FieldType.SELECT,
            FieldType.RADIO,
            FieldType.CHECKLIST,
        ):
            continue
        if coerced is None:
            coerced = raw
        initial[f"f_{ff.pk}"] = coerced

    return initial
