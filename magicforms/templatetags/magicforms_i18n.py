"""Template helpers for translating database-stored user copy."""

from __future__ import annotations

import re

from django import template

from ..i18n_db import gettext_db
from ..timeline_i18n import (
    timeline_event_kind_label,
    timeline_event_message_display,
    timeline_event_step_label,
)

register = template.Library()

_NA_PLACEHOLDER_NORMALIZED = frozenset(
    {
        "not applicable",
        "not-applicable",
        "not_applicable",
        "n/a",
        "n.a.",
        "n.a",
    }
)


def _normalize_answer_placeholder(raw: str) -> str:
    s = str(raw).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("−", "-").replace("–", "-")
    return s


@register.filter(name="intro_html", is_safe=True)
def intro_html(value) -> str:
    """Sanitize and render announcement page message HTML."""
    from ..intro_page import intro_description_markup

    return intro_description_markup(value)


@register.filter(name="mf_trans")
def mf_trans(value) -> str:
    """Looks up ``value`` in the active Django translation catalog (like ``gettext``)."""
    if value is None:
        return ""
    return gettext_db(str(value))


@register.filter(name="mf_timeline_kind")
def mf_timeline_kind(event) -> str:
    return timeline_event_kind_label(event)


@register.filter(name="mf_timeline_message")
def mf_timeline_message(event) -> str:
    step_label = None
    if getattr(event, "step_id", None) and getattr(event, "step", None):
        step_label = event.step.label
    return timeline_event_message_display(event.message, step_label=step_label)


@register.filter(name="mf_timeline_step")
def mf_timeline_step(step) -> str:
    return timeline_event_step_label(step)


@register.filter(name="mf_is_na_placeholder")
def mf_is_na_placeholder(value) -> bool:
    """
    True when a stored text answer is a generic “not applicable” style placeholder.
    Submission views use this to hide those rows so they do not clutter the page.
    """
    if value is None:
        return False
    normalized = _normalize_answer_placeholder(value)
    if not normalized:
        return False
    return normalized in _NA_PLACEHOLDER_NORMALIZED
