"""Resolve applicant email from a submission and send studio messages."""

from __future__ import annotations

from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from .models import FieldType, FormSubmission
from .outbound.applicant_data import resolve_applicant_value


def _is_valid_email(addr: str) -> bool:
    addr = (addr or "").strip()
    if not addr:
        return False
    try:
        validate_email(addr)
        return True
    except ValidationError:
        return False


def applicant_email_source_label(source: str, *, field_label: str = "") -> str:
    if source == "submitter_email":
        return str(_("email on file for this submission"))
    if source == "account":
        return str(_("signed-in applicant account email"))
    if source.startswith("field:"):
        label = (field_label or "").strip() or source.split(":", 1)[-1]
        return str(_("form field “%(label)s”") % {"label": label})
    return ""


def applicant_email_candidates(submission: FormSubmission) -> list[tuple[str, str, str]]:
    """
    Ordered ``(email, source_key, field_label)`` candidates for the send-mail form.
    Form ``email`` field answers are preferred, then submission/account addresses.
    """
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []

    def add(addr: str, source: str, field_label: str = "") -> None:
        addr = (addr or "").strip()
        key = addr.casefold()
        if not _is_valid_email(addr) or key in seen:
            return
        seen.add(key)
        out.append((addr, source, field_label))

    values = list(submission.values.all())
    values.sort(key=lambda v: (v.field.order, v.field_id))
    for sv in values:
        if sv.field.field_type != FieldType.EMAIL:
            continue
        add(sv.value, f"field:{sv.field.name}", sv.field.label)

    add(submission.submitter_email or "", "submitter_email")
    add(resolve_applicant_value(submission, "email"), "account")

    return out


def default_applicant_email(submission: FormSubmission) -> tuple[str, str, str]:
    """``(email, source_key, field_label)`` — empty strings when none found."""
    candidates = applicant_email_candidates(submission)
    if not candidates:
        return "", "", ""
    return candidates[0]


def default_applicant_email_subject(submission: FormSubmission) -> str:
    title = (submission.form.title or "").strip() or _("Form")
    ref = str(submission.reference_token)
    return str(_("Regarding your submission — %(form)s (%(ref)s)") % {"form": title, "ref": ref[:8]})


def send_applicant_email(
    submission: FormSubmission,
    *,
    to_email: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> None:
    """Send using the submission form's organization mail settings."""
    from .entity_email import entity_for_submission, send_organization_email

    send_organization_email(
        entity_for_submission(submission),
        to=to_email,
        subject=subject,
        body=body,
        reply_to=reply_to,
    )
