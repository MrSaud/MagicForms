#!/usr/bin/env python3
"""Apply hand-written Arabic translations to locale/ar/LC_MESSAGES/django.po."""
from __future__ import annotations

import sys
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ar_gaps_data import FUZZY_FIXES, PLURALS, TIMELINE_PCONTEXT, TRANSLATIONS  # noqa: E402


def apply_plural(entry: polib.POEntry, forms: dict[str, str]) -> None:
    for idx, text in forms.items():
        entry.msgstr_plural[int(idx)] = text
    entry.fuzzy = False


def main() -> None:
    path = str(ROOT / "locale/ar/LC_MESSAGES/django.po")
    po = polib.pofile(path)
    filled = fuzzy_cleared = plural_filled = ctxt_filled = 0

    for ctxt, mapping in TIMELINE_PCONTEXT.items():
        for mid, mstr in mapping.items():
            entry = po.find(mid, msgctxt=ctxt)
            if entry is None:
                entry = polib.POEntry(msgctxt=ctxt, msgid=mid, msgstr=mstr)
                po.append(entry)
                ctxt_filled += 1
            elif not (entry.msgstr or "").strip():
                entry.msgstr = mstr
                entry.fuzzy = False
                ctxt_filled += 1

    for entry in po:
        if entry.obsolete:
            continue
        mid = entry.msgid
        if not mid:
            continue

        if entry.msgid_plural and mid in PLURALS:
            apply_plural(entry, PLURALS[mid])
            plural_filled += 1
            continue

        fix = FUZZY_FIXES.get(mid)
        if fix is not None:
            entry.msgstr = fix
            entry.fuzzy = False
            fuzzy_cleared += 1
            continue

        if entry.fuzzy and mid in TRANSLATIONS:
            entry.msgstr = TRANSLATIONS[mid]
            entry.fuzzy = False
            fuzzy_cleared += 1
            continue

        if not (entry.msgstr or "").strip() and mid in TRANSLATIONS:
            entry.msgstr = TRANSLATIONS[mid]
            entry.fuzzy = False
            filled += 1

    if po.metadata:
        po.metadata["Language"] = "ar"
    po.save(path)
    print(f"filled={filled} fuzzy_fixed={fuzzy_cleared} plurals={plural_filled} ctxt={ctxt_filled}")


if __name__ == "__main__":
    main()
