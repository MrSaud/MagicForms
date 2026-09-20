"""Parse ``entity-slug-username`` login identifiers (studio + mobile API)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedLoginIdentity:
    entity_slug: str | None
    username: str


def parse_login_identity(raw: str, known_entity_slugs: list[str]) -> ParsedLoginIdentity:
    """
    Split ``{slug}-{username}`` using the longest matching directory organization slug.

    Example: ``mosa-kuwait-jdoe`` → slug ``mosa-kuwait``, username ``jdoe``.
    """
    trimmed = (raw or "").strip()
    if not trimmed:
        return ParsedLoginIdentity(entity_slug=None, username="")

    slugs = sorted(
        {s.strip() for s in known_entity_slugs if (s or "").strip()},
        key=len,
        reverse=True,
    )
    lower = trimmed.lower()
    for slug in slugs:
        prefix = f"{slug}-"
        if lower.startswith(prefix.lower()):
            username = trimmed[len(prefix) :].strip()
            if username:
                return ParsedLoginIdentity(entity_slug=slug, username=username)

    return ParsedLoginIdentity(entity_slug=None, username=trimmed)
