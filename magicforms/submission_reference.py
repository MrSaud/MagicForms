"""Allocate unique public submission track codes: ``yymmdd`` + minute-of-hour + 6 random digits (14 characters)."""

from __future__ import annotations

import random
from typing import Type

from django.db.models import Model
from django.utils import timezone


def generate_submission_reference_token(model_cls: Type[Model], *, max_attempts: int = 128) -> str:
    """
    Wall-clock prefix in the active timezone: ``%y%m%d`` (``yymmdd``) plus ``%M`` (two-digit minute),
    then six random decimal digits (14 characters total).
    Uniqueness is checked against ``model_cls`` rows' ``reference_token`` field.
    """
    for _ in range(max_attempts):
        prefix = timezone.localtime(timezone.now()).strftime("%y%m%d%M")
        candidate = f"{prefix}{random.randint(0, 999_999):06d}"
        if not model_cls.objects.filter(reference_token=candidate).exists():
            return candidate
    msg = "Could not allocate a unique submission reference_token"
    raise RuntimeError(msg)
