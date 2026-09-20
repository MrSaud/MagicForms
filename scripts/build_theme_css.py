#!/usr/bin/env python3
"""
Concatenate magicforms/static/magicforms/css/src/*.css (in name order) into theme.css.

theme.css is the single file nginx serves; the src/ parts are what you edit. Run this after
editing any part (the test suite fails if theme.css is stale):

    python scripts/build_theme_css.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "magicforms/static/magicforms/css/src"
OUT = ROOT / "magicforms/static/magicforms/css/theme.css"
HEADER = "/* GENERATED FILE — edit magicforms/static/magicforms/css/src/*.css and run scripts/build_theme_css.py */\n\n"


def build() -> str:
    parts = sorted(p for p in SRC.glob("*.css"))
    chunks = []
    for p in parts:
        chunks.append(f"/* ===== {p.name} ===== */\n" + p.read_text(encoding="utf-8").rstrip("\n") + "\n")
    return HEADER + "\n".join(chunks)


def main(argv: list[str]) -> int:
    built = build()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != built:
            print("theme.css is stale: run scripts/build_theme_css.py", file=sys.stderr)
            return 1
        print("theme.css is up to date")
        return 0
    OUT.write_text(built, encoding="utf-8")
    print(f"wrote {OUT} ({len(built)} bytes) from {len(list(SRC.glob('*.css')))} parts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
