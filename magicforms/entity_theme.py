"""Build safe inline CSS custom properties from ``Entity`` theme presets."""

from __future__ import annotations

import re

HEX7 = re.compile(r"^#[0-9A-Fa-f]{6}$")

THEME_SLOT_COUNT = 3


def default_theme_presets() -> list[dict[str, str]]:
    """Three independent portal theme slots (primary / secondary / background tint)."""
    blank = {"primary": "#0071e3", "secondary": "", "background": ""}
    return [dict(blank), dict(blank), dict(blank)]


def normalize_theme_presets(raw) -> list[dict[str, str]]:
    """Return exactly ``THEME_SLOT_COUNT`` dicts with string keys primary, secondary, background."""
    base = default_theme_presets()
    if not isinstance(raw, list):
        return [dict(x) for x in base]
    out: list[dict[str, str]] = []
    for i in range(THEME_SLOT_COUNT):
        if i < len(raw) and isinstance(raw[i], dict):
            slot = raw[i]
            out.append(
                {
                    "primary": (slot.get("primary") or "#0071e3").strip()[:7],
                    "secondary": (slot.get("secondary") or "").strip()[:7],
                    "background": (slot.get("background") or "").strip()[:7],
                }
            )
        else:
            out.append(dict(base[i]))
    return out


def active_theme_slot(entity) -> dict[str, str]:
    """The preset currently used for the public portal (validated structure, not hex)."""
    if entity is None:
        return dict(default_theme_presets()[0])
    idx = max(0, min(int(getattr(entity, "active_theme_index", 0) or 0), THEME_SLOT_COUNT - 1))
    presets = normalize_theme_presets(getattr(entity, "theme_presets", None))
    return dict(presets[idx])


def sanitize_hex7(value: str | None, default: str) -> str:
    v = (value or "").strip()
    return v if HEX7.match(v) else default


def portal_theme_inline(entity) -> str:
    """
    Space-separated CSS declarations for use in a ``style`` attribute on ``.mf-shell``.
    Only validated #RRGGBB values are emitted.
    """
    if entity is None:
        return ""
    slot = active_theme_slot(entity)
    accent = sanitize_hex7(slot.get("primary"), "#0071e3")
    secondary_raw = (slot.get("secondary") or "").strip()
    secondary = sanitize_hex7(secondary_raw, accent) if secondary_raw else accent
    bg = (slot.get("background") or "").strip()
    parts = [
        f"--mf-accent: {accent};",
        f"--mf-accent-secondary: {secondary};",
        f"--mf-hint-accent-tint: color-mix(in srgb, {accent} 12%, transparent);",
        f"--mf-hint-border: color-mix(in srgb, {accent} 14%, rgba(0, 0, 0, 0.06));",
    ]
    if bg and HEX7.match(bg):
        parts.append(f"--mf-bg0: {bg};")
        parts.append(f"--mf-bg1: {bg};")
        parts.append(
            f"--mf-hint-surface: color-mix(in srgb, {bg} 42%, rgba(255, 255, 255, 0.78));"
        )
    return " ".join(parts)


def entity_notifications_may_send(entity) -> bool:
    """
    Whether automated notifications (including email) may run for this organization.

    Email delivery uses organization SMTP via :mod:`magicforms.entity_email`; callers
    sending mail should use :func:`entity_email.entity_email_notifications_ready` or
    :func:`send_organization_email` directly.
    """
    if entity is None:
        return False
    if not entity.notifications_enabled:
        return False
    from .entity_email import entity_email_notifications_ready

    ok, _msg = entity_email_notifications_ready(entity)
    return ok


def entity_email_may_send(entity) -> bool:
    """Whether this organization is configured to send email."""
    return entity_notifications_may_send(entity)
