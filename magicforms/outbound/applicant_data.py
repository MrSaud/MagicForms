"""Applicant (submitter) attributes for outbound field mapping."""

from __future__ import annotations

from django.db import models

from magicforms.models import EmployeeProfile, FormSubmission
from magicforms.user_mapping import resolve_mapping_raw


def applicant_attribute_catalog() -> list[tuple[str, str]]:
    """
    ``(key, label)`` for the mapping UI — account fields plus ``EmployeeProfile`` columns.
    """
    rows: list[tuple[str, str]] = [
        ("email", "Email"),
        ("username", "Username"),
        ("first_name", "First name"),
        ("last_name", "Last name"),
        ("full_name", "Full name"),
    ]
    seen = {k for k, _ in rows}
    for field in EmployeeProfile._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        if field.name in ("user", "manager"):
            continue
        if not isinstance(
            field,
            (
                models.CharField,
                models.EmailField,
                models.DateField,
                models.DateTimeField,
                models.TextField,
            ),
        ):
            continue
        if field.name in seen:
            continue
        seen.add(field.name)
        label = str(getattr(field, "verbose_name", None) or field.name).strip()
        rows.append((field.name, label))
    rows.append(("manager_username", "Manager username"))
    return sorted(rows, key=lambda x: (x[0] != "email", x[1].lower()))


def applicant_attribute_keys() -> frozenset[str]:
    return frozenset(k for k, _ in applicant_attribute_catalog())


def resolve_applicant_value(submission: FormSubmission, key: str) -> str:
    """
    Value from the submitter's account / ``EmployeeProfile`` (when they were signed in).
    Anonymous submissions only populate ``email`` from ``submission.submitter_email``.
    """
    key = (key or "").strip()
    if not key:
        return ""

    user = submission.submitted_by
    if user is None:
        if key.lower().replace("-", "_") in ("email", "submitter_email"):
            return (submission.submitter_email or "").strip()
        return ""

    key_norm = key.lower().replace("-", "_")
    if key_norm == "manager_username":
        profile = getattr(user, "profile", None)
        if profile is not None and profile.manager_id:
            mgr = profile.manager
            return (getattr(mgr, "username", None) or "").strip()
        return ""

    raw = resolve_mapping_raw(user, key)
    if raw is not None:
        return raw

    profile = getattr(user, "profile", None)
    if profile is not None:
        for attr in (key, key_norm, key.replace("-", "_")):
            if hasattr(profile, attr):
                v = getattr(profile, attr)
                if v is None or v == "":
                    continue
                if hasattr(v, "isoformat"):
                    return v.isoformat()
                return str(v).strip()

    if key_norm == "email":
        return (getattr(user, "email", None) or submission.submitter_email or "").strip()
    return ""
