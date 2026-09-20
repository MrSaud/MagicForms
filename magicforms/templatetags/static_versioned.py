"""``{% static_v 'path' %}``: static URL with a content hash query string, so browsers and nginx caches
pick up new CSS/JS on deploy without hard refreshes."""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@lru_cache(maxsize=256)
def _version(path: str) -> str:
    try:
        found = finders.find(path)
        if found:
            with open(found, "rb") as fh:
                return hashlib.md5(fh.read()).hexdigest()[:10]
    except OSError:
        pass
    return "0"


@register.simple_tag
def static_v(path: str) -> str:
    url = static(path)
    version = _version(path) if not os.environ.get("MAGIFORM_STATIC_NO_VERSION") else "dev"
    return f"{url}?v={version}"
