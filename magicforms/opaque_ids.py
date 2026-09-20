"""
Opaque ids for studio links (``/manage/forms/k7q2m9x/`` instead of ``/manage/forms/2/``).

A keyed Feistel permutation (HMAC-SHA256 over ``SECRET_KEY``) maps every 32-bit integer to another
32-bit integer, which is written as exactly seven Crockford-style base-32 characters. Tokens look random,
are not guessable without the key, and decode back to the database id. Plain integers never appear in
studio URLs; the path converter only accepts seven-character tokens, so old numeric links 404.
"""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
_INDEX = {c: i for i, c in enumerate(_ALPHABET)}
TOKEN_LENGTH = 7
TOKEN_REGEX = "[0-9a-hj-km-np-tv-z]{%d}" % TOKEN_LENGTH
_ROUNDS = 4
_MASK16 = 0xFFFF


def _round_key(round_no: int, half: int) -> int:
    key = settings.SECRET_KEY.encode("utf-8")
    msg = b"magicforms-oid:%d:%d" % (round_no, half)
    return int.from_bytes(hmac.new(key, msg, hashlib.sha256).digest()[:2], "big")


def _permute(value: int, *, inverse: bool = False) -> int:
    left, right = (value >> 16) & _MASK16, value & _MASK16
    rounds = range(_ROUNDS - 1, -1, -1) if inverse else range(_ROUNDS)
    for r in rounds:
        left, right = right, left ^ _round_key(r, right)
    # undo the final swap so the permutation is its own structure both ways
    left, right = right, left
    return (left << 16) | right


def encode(pk: int) -> str:
    n = int(pk)
    if n < 0 or n > 0xFFFFFFFF:
        raise ValueError("id out of range for opaque encoding")
    v = _permute(n)
    out = []
    for _ in range(TOKEN_LENGTH):
        out.append(_ALPHABET[v & 31])
        v >>= 5
    return "".join(reversed(out))


def decode(token: str) -> int | None:
    if not isinstance(token, str) or len(token) != TOKEN_LENGTH:
        return None
    v = 0
    for ch in token:
        i = _INDEX.get(ch)
        if i is None:
            return None
        v = (v << 5) | i
    if v > 0xFFFFFFFF:
        return None
    return _permute(v, inverse=True)


def parse_id(raw) -> int | None:
    """Query-string / form value: an opaque token, or (for old bookmarks and API clients) a plain integer."""
    s = (str(raw) if raw is not None else "").strip()
    if not s:
        return None
    if len(s) == TOKEN_LENGTH and not s.isdigit():
        return decode(s)
    if s.isdigit():
        return int(s)
    return decode(s)


class OpaqueIdConverter:
    """URL path converter ``<oid:pk>``: opaque token in the URL, integer in the view."""

    regex = TOKEN_REGEX

    def to_python(self, value):
        pk = decode(value)
        if pk is None:
            raise ValueError("bad opaque id")
        return pk

    def to_url(self, value):
        if isinstance(value, str) and len(value) == TOKEN_LENGTH and not value.isdigit() and decode(value) is not None:
            return value
        return encode(int(value))
