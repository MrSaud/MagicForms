#!/usr/bin/env python3
"""
Rebuild ``magicforms/sample_forms_ar.json`` from ``sample_forms_library`` English strings.

Requires ``deep-translator`` (not a runtime dependency of MagicForms):

    pip install deep-translator
    python scripts/regenerate_sample_forms_ar_json.py

Run after adding or editing sample form titles, descriptions, labels, help text, or choices.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deep_translator import GoogleTranslator  # noqa: E402

from magicforms.sample_forms_library import SAMPLE_ENTITY_NAME, SAMPLE_CATEGORIES, _form_specs  # noqa: E402


def collect_strings() -> set[str]:
    strings: set[str] = set()
    strings.add(SAMPLE_ENTITY_NAME)
    for _slug, name, _order in SAMPLE_CATEGORIES:
        strings.add(name)
    for spec in _form_specs():
        strings.add(spec["title"])
        d = spec.get("description") or ""
        if d:
            strings.add(d)
        for row in spec["fields"]:
            _n, _t, label, _req, help_text, choices = row
            strings.add(label)
            if help_text:
                strings.add(help_text)
            if choices:
                for line in choices.splitlines():
                    line = line.strip()
                    if line:
                        strings.add(line)
    strings.add("New")
    strings.add("Initial step for new submissions.")
    return strings


def main() -> None:
    ordered = [s for s in sorted(collect_strings(), key=lambda x: (len(x), x)) if s.strip()]
    tr = GoogleTranslator(source="en", target="ar")
    chunk_size = 25
    out: dict[str, str] = {}
    for i in range(0, len(ordered), chunk_size):
        chunk = ordered[i : i + chunk_size]
        blob = "\n".join(chunk)
        try:
            translated = tr.translate(blob)
        except Exception as exc:
            print("chunk translate failed", i, exc, file=sys.stderr)
            for s in chunk:
                try:
                    out[s] = tr.translate(s)
                except Exception:
                    out[s] = s
            continue
        parts = translated.split("\n")
        if len(parts) != len(chunk):
            print("line count mismatch at", i, "— per-string fallback", file=sys.stderr)
            for s in chunk:
                try:
                    out[s] = tr.translate(s)
                except Exception:
                    out[s] = s
        else:
            for s, ar in zip(chunk, parts):
                out[s] = ar

    need = {s for s in collect_strings() if s.strip()}
    missing = need - set(out.keys())
    if missing:
        print("still missing", len(missing), file=sys.stderr)
        for s in missing:
            try:
                out[s] = tr.translate(s)
            except Exception:
                out[s] = s

    out_path = ROOT / "magicforms" / "sample_forms_ar.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print("wrote", out_path, "entries", len(out))


if __name__ == "__main__":
    main()
