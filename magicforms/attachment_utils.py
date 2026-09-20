"""Rules for submission attachment delete and PDF preview (LibreOffice)."""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser

from .models import FormSubmission, SubmissionAttachment


def attachment_source_ext_for_pdf(attachment: SubmissionAttachment) -> str | None:
    """Return lower extension if this file can be converted to PDF via LibreOffice, else None."""
    name = (attachment.file.name or "").lower()
    for ext in ("docx", "odt", "doc"):
        if name.endswith("." + ext):
            return ext
    return None


def attachment_may_delete_on_manage(user: AbstractUser, _submission: FormSubmission, attachment: SubmissionAttachment) -> bool:
    """Studio submission detail: only the uploader may remove their own staff upload; respondent uploads handled on track or by superuser."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if attachment.uploaded_by_id:
        return attachment.uploaded_by_id == user.pk
    return False


def attachment_may_delete_on_track(
    user: AbstractUser | None,
    submission: FormSubmission,
    attachment: SubmissionAttachment,
) -> bool:
    """
    Public track page: staff may remove only files they uploaded while signed in; respondent files
    only the account that submitted may remove; anonymous submissions may remove respondent uploads
    with the same secret link (no stronger identity).
    """
    if attachment.uploaded_by_id:
        return bool(user and user.is_authenticated and attachment.uploaded_by_id == user.pk)
    if submission.submitted_by_id:
        return bool(user and user.is_authenticated and submission.submitted_by_id == user.pk)
    return True
