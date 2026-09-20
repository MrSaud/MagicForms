"""
Outbound email for MagicForms — always per-organization SMTP.

All application email (studio applicant mail, future notification hooks, etc.)
must call :func:`send_organization_email` or :func:`send_entity_email` with the
organization tied to the form/submission. Global ``EMAIL_*`` in Django settings
is not used for tenant mail.
"""

from __future__ import annotations

from email.utils import formataddr, parseaddr

from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext as _

from .models import Entity, Form, FormSubmission


def _is_valid_email(addr: str) -> bool:
    addr = (addr or "").strip()
    if not addr:
        return False
    try:
        validate_email(addr)
        return True
    except ValidationError:
        return False


def entity_for_submission(submission: FormSubmission) -> Entity:
    return submission.form.entity


def entity_for_form(form: Form | int) -> Entity:
    if isinstance(form, Form):
        return form.entity
    return Form.objects.select_related("entity").get(pk=int(form)).entity


def entity_email_notifications_ready(entity: Entity | None) -> tuple[bool, str]:
    """
    Return ``(ok, message)`` — whether this organization may send email.
    ``message`` is a user-facing reason when ``ok`` is false.
    """
    if entity is None:
        return False, str(_("Organization not found."))
    if not entity.email_notifications_enabled:
        return False, str(
            _(
                "Email is turned off for this organization. "
                "A superuser can enable it under Organizations → Settings → Email notifications."
            )
        )
    if not entity.notifications_enabled:
        return False, str(
            _(
                "Notifications are disabled for this organization. "
                "Enable notifications and email settings under Organizations → Settings."
            )
        )
    if not (entity.email_from_address or "").strip():
        return False, str(_("Set a From address in organization email settings."))
    if not (entity.email_smtp_host or "").strip():
        return False, str(_("Set an SMTP host in organization email settings."))
    port = entity.email_smtp_port or 0
    if port < 1 or port > 65535:
        return False, str(_("Set a valid SMTP port (1–65535) in organization email settings."))
    addr = entity_email_from_parsed(entity)
    if not addr:
        return False, str(_("The From address is not a valid email address."))
    if not (entity.email_smtp_password or "").strip() and not (entity.email_smtp_username or "").strip():
        pass  # allow open relay / local SMTP without auth
    elif (entity.email_smtp_username or "").strip() and not (entity.email_smtp_password or "").strip():
        return False, str(_("Set an SMTP password or clear the SMTP username in organization email settings."))
    return True, ""


def entity_email_from_header(entity: Entity) -> str:
    """Formatted From header from organization settings only."""
    return (entity.email_from_address or "").strip()


def entity_email_from_parsed(entity: Entity) -> str:
    """Bare email address from ``email_from_address``."""
    _name, addr = parseaddr(entity_email_from_header(entity))
    return (addr or "").strip()


def entity_email_reply_to(entity: Entity, *, extra_reply_to: str | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in (
        (entity.email_reply_to or "").strip(),
        (extra_reply_to or "").strip(),
    ):
        if raw and _is_valid_email(raw) and raw.casefold() not in seen:
            seen.add(raw.casefold())
            out.append(raw)
    return out


def get_entity_smtp_connection(entity: Entity):
    """SMTP connection using this organization's host, port, TLS/SSL, and credentials."""
    use_ssl = bool(entity.email_smtp_use_ssl)
    use_tls = bool(entity.email_smtp_use_tls) and not use_ssl
    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=(entity.email_smtp_host or "").strip(),
        port=int(entity.email_smtp_port or 587),
        username=(entity.email_smtp_username or "").strip() or None,
        password=(entity.email_smtp_password or "").strip() or None,
        use_tls=use_tls,
        use_ssl=use_ssl,
        fail_silently=False,
    )


def _normalize_recipients(to: str | list[str]) -> list[str]:
    if isinstance(to, str):
        raw = [to]
    else:
        raw = list(to)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        addr = (item or "").strip()
        if _is_valid_email(addr) and addr.casefold() not in seen:
            seen.add(addr.casefold())
            out.append(addr)
    if not out:
        raise ValueError("No valid recipient email addresses.")
    return out


def send_organization_email(
    entity: Entity,
    *,
    to: str | list[str],
    subject: str,
    body: str,
    reply_to: str | None = None,
    html_body: str | None = None,
) -> None:
    """
    Send mail through the organization's SMTP configuration.

    Raises ``RuntimeError`` when email is disabled or misconfigured.
    """
    ok, err = entity_email_notifications_ready(entity)
    if not ok:
        raise RuntimeError(err)

    recipients = _normalize_recipients(to)
    reply_list = entity_email_reply_to(entity, extra_reply_to=reply_to)
    connection = get_entity_smtp_connection(entity)
    from_email = entity_email_from_header(entity)
    subj = subject.strip()[:200]
    text = body.strip()

    if html_body:
        msg = EmailMultiAlternatives(
            subject=subj,
            body=text,
            from_email=from_email,
            to=recipients,
            reply_to=reply_list or None,
            connection=connection,
        )
        msg.attach_alternative(html_body.strip(), "text/html")
    else:
        msg = EmailMessage(
            subject=subj,
            body=text,
            from_email=from_email,
            to=recipients,
            reply_to=reply_list or None,
            connection=connection,
        )
    msg.send(fail_silently=False)


def send_entity_email(
    entity: Entity,
    *,
    to_email: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> None:
    """Backward-compatible single-recipient plain-text send."""
    send_organization_email(
        entity,
        to=to_email,
        subject=subject,
        body=body,
        reply_to=reply_to,
    )


def format_from_address(display_name: str, email: str) -> str:
    """Build ``Name <email@example.com>`` for storage."""
    display_name = (display_name or "").strip()
    email = (email or "").strip()
    if display_name and email:
        return formataddr((display_name, email))
    return email
