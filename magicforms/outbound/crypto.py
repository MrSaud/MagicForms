"""Encrypt outbound API secrets at rest (Fernet derived from Django secret)."""

from __future__ import annotations

import base64
import hashlib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_FERNET = None


def _fernet():
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise ImproperlyConfigured(
            "Install the cryptography package to use outbound API secrets."
        ) from exc
    extra = (getattr(settings, "OUTBOUND_WEBHOOK_FERNET_KEY", "") or "").strip()
    seed = extra or settings.SECRET_KEY
    key = base64.urlsafe_b64encode(hashlib.sha256(f"{seed}:mf-outbound-v1".encode()).digest())
    _FERNET = Fernet(key)
    return _FERNET


def encrypt_secret(plain: str) -> str:
    plain = (plain or "").strip()
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    ciphertext = (ciphertext or "").strip()
    if not ciphertext:
        return ""
    return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
