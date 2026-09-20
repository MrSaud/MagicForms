"""Translate user-defined copy from the database (labels, placeholders, etc.).

Use the same strings as ``msgid`` in ``locale/*/LC_MESSAGES/django.po``.
``makemessages`` does not extract these automatically; add entries when forms are defined.

When the active UI language is Arabic, known **sample form** English strings (see
``magicforms/sample_forms_ar.json``) are translated before the gettext catalog so starter
templates show Arabic without changing stored English in the database. Regenerate that JSON
with ``scripts/regenerate_sample_forms_ar_json.py`` after editing ``sample_forms_library``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from django.utils import translation
from django.utils.translation import gettext


@lru_cache(maxsize=1)
def _sample_forms_ar_map() -> dict[str, str]:
    path = Path(__file__).resolve().parent / "sample_forms_ar.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return {}


def gettext_db(text: str | None) -> str:
    if text is None:
        return ""
    s = str(text)
    if not s.strip():
        return s
    lang = (translation.get_language() or "").split("-")[0].lower()
    if lang == "ar":
        ar_map = _sample_forms_ar_map()
        if s in ar_map:
            return ar_map[s]
    return gettext(s)
