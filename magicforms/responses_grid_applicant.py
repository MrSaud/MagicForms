"""Applicant (requester) display values for the responses grid and studio lists."""

from __future__ import annotations

from django.utils.translation import gettext as _

from magicforms.models import FormSubmission
from magicforms.outbound.applicant_data import resolve_applicant_value
from magicforms.submission_applicant_email import applicant_email_candidates

# Guest submissions: first matching form field (by ``name`` or ``mapping_key``) wins.
GUEST_IDENTITY_FIELD_KEYS: tuple[str, ...] = ("name", "username", "requester", "applicant", "email")


def _normalize_field_key(raw: str) -> str:
    return (raw or "").strip().lower().replace("-", "_")


def _field_identity_keys(field) -> set[str]:
    keys: set[str] = set()
    for raw in (field.name, getattr(field, "mapping_key", None)):
        if raw:
            keys.add(_normalize_field_key(raw))
    return keys


def _best_applicant_email(submission: FormSubmission) -> str:
    candidates = applicant_email_candidates(submission)
    if candidates:
        return candidates[0][0]
    return (submission.submitter_email or "").strip()


def applicant_meta_values(submission: FormSubmission) -> dict[str, str]:
    """
    Values for ``meta:applicant*`` and improved ``meta:email`` / ``meta:account`` cells.
    """
    email = _best_applicant_email(submission)
    username = ""
    name = ""

    user = submission.submitted_by
    if user is not None:
        username = (user.get_username() or "").strip()
        name = (
            resolve_applicant_value(submission, "full_name")
            or (user.get_full_name() or "").strip()
        )
        if not email:
            email = resolve_applicant_value(submission, "email")

    display = ""
    if name and email:
        display = f"{name} ({email})"
    elif name:
        display = name
    elif email:
        display = email
    elif username:
        display = username
    else:
        display = ""

    return {
        "applicant": display,
        "applicant_name": name,
        "email": email,
        "account": username,
    }


def guest_identity_field_display(submission: FormSubmission) -> tuple[str, str] | None:
    """
    For anonymous submitters: ``(field_label, answer)`` from the first non-empty guest
    identity field on the form (priority: name → username → requester → applicant → email).
    """
    by_key: dict[str, tuple[str, str]] = {}
    for sv in submission.values.all():
        val = (sv.value or "").strip()
        if not val:
            continue
        label = (sv.field.label or sv.field.name or "").strip()
        for key in _field_identity_keys(sv.field):
            if key in GUEST_IDENTITY_FIELD_KEYS and key not in by_key:
                by_key[key] = (label, val)
    for key in GUEST_IDENTITY_FIELD_KEYS:
        if key in by_key:
            return by_key[key]
    return None


def inbox_applicant_labels(submission: FormSubmission) -> tuple[str, str]:
    """Account username and first name for studio inbox / submission search list rows."""
    user = submission.submitted_by
    if user is not None:
        username = (user.get_username() or "").strip()
        first_name = (user.first_name or "").strip()
        if not first_name:
            first_name = (resolve_applicant_value(submission, "first_name") or "").strip()
        return username, first_name
    first_name = (resolve_applicant_value(submission, "first_name") or "").strip()
    return "", first_name


def _inbox_applicant_has_display_value(submission: FormSubmission) -> bool:
    return bool(
        (submission.inbox_applicant_guest_value or "").strip()
        or (submission.inbox_applicant_username or "").strip()
        or (submission.inbox_applicant_first_name or "").strip()
    )


def _apply_inbox_applicant_anonymous_fallback(submission: FormSubmission) -> None:
    """When a row shows a prefix but no name/email, display a translated Anonymous label."""
    if not (submission.inbox_applicant_prefix or "").strip():
        return
    if _inbox_applicant_has_display_value(submission):
        return
    submission.inbox_applicant_guest_value = _("Anonymous")


def attach_studio_list_applicant(submission: FormSubmission) -> None:
    """Set ``inbox_applicant_*`` attributes for list templates (call under active locale)."""
    requested_by = _("Requested by:")
    user = submission.submitted_by
    if user is not None:
        username, first_name = inbox_applicant_labels(submission)
        submission.inbox_applicant_prefix = requested_by
        submission.inbox_applicant_prefix_is_field_label = False
        submission.inbox_applicant_username = username
        submission.inbox_applicant_first_name = first_name
        submission.inbox_applicant_guest_value = ""
        _apply_inbox_applicant_anonymous_fallback(submission)
        return

    guest = guest_identity_field_display(submission)
    if guest:
        label, val = guest
        submission.inbox_applicant_prefix = label
        submission.inbox_applicant_prefix_is_field_label = True
        submission.inbox_applicant_username = ""
        submission.inbox_applicant_first_name = ""
        submission.inbox_applicant_guest_value = val
        return

    _unused_username, first_name = inbox_applicant_labels(submission)
    submission.inbox_applicant_prefix = requested_by
    submission.inbox_applicant_prefix_is_field_label = False
    submission.inbox_applicant_username = ""
    submission.inbox_applicant_first_name = first_name
    submission.inbox_applicant_guest_value = (submission.submitter_email or "").strip()
    _apply_inbox_applicant_anonymous_fallback(submission)
