#!/usr/bin/env python3
"""Fill Arabic msgstr in locale/ar/LC_MESSAGES/django.po via deep-translator."""
import re
import time

import polib
from deep_translator import GoogleTranslator


def has_format_tokens(s: str) -> bool:
    return bool(re.search(r"%\(|%\w|{{\s*\w", s))


def translate_safe(tr: GoogleTranslator, text: str) -> str:
    if not text.strip():
        return text
    try:
        return tr.translate(text)
    except Exception:
        return text


def main() -> None:
    path = "locale/ar/LC_MESSAGES/django.po"
    po = polib.pofile(path)
    tr = GoogleTranslator(source="en", target="ar")
    for i, entry in enumerate(po):
        if entry.msgid_plural:
            if not any((entry.msgstr_plural or {}).values()):
                s0 = translate_safe(tr, entry.msgid)
                time.sleep(0.12)
                s1 = translate_safe(tr, entry.msgid_plural)
                time.sleep(0.12)
                for k in range(6):
                    entry.msgstr_plural[k] = s0 if k == 0 else s1
            continue

        mid = entry.msgid
        if not mid or not mid.strip():
            continue
        if entry.msgstr and entry.msgstr.strip():
            continue
        if has_format_tokens(mid):
            entry.msgstr = mid
            continue
        entry.msgstr = translate_safe(tr, mid)
        time.sleep(0.1)
        if (i + 1) % 20 == 0:
            print(f"... {i + 1}")

    if po.metadata:
        po.metadata["Language"] = "ar"
    po.save(path)
    print("done")


if __name__ == "__main__":
    main()
