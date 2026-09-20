"""
Applicant notification emails: templates, rendering, and dispatch.

All sends use the organization's SMTP via :mod:`magicforms.entity_email`.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from .entity_email import send_organization_email
from .entity_theme import entity_notifications_may_send
from .models import (
    Entity,
    EntityEmailNotificationBehavior,
    EntityEmailNotificationTemplate,
    FormSubmission,
    SubmissionEvent,
)
from .submission_applicant_email import applicant_email_candidates, default_applicant_email

logger = logging.getLogger(__name__)

PLACEHOLDER_HELP = (
    "{{form_title}}, {{entity_name}}, {{reference}}, {{submitted_at}}, "
    "{{applicant_email}}, {{workflow_state}}, {{current_step}}, {{decision_comment}}, "
    "{{track_url}}, {{staff_name}}"
)

_EVENT_TO_TEMPLATE_KIND: dict[str, str] = {
    SubmissionEvent.Kind.SUBMITTED: EntityEmailNotificationTemplate.Kind.SUBMITTED,
    SubmissionEvent.Kind.WORKFLOW_COMPLETED: EntityEmailNotificationTemplate.Kind.ACCEPTED,
    SubmissionEvent.Kind.WORKFLOW_REJECTED: EntityEmailNotificationTemplate.Kind.REJECTED,
    SubmissionEvent.Kind.STEP_APPROVED: EntityEmailNotificationTemplate.Kind.ACCEPTED,
}

_DEFAULT_COPY: dict[str, tuple[str, str]] = {
    EntityEmailNotificationTemplate.Kind.SUBMITTED: (
        _("Your submission to {{form_title}} was received"),
        _(
            "Hello,\n\n"
            "We received your submission.\n\n"
            "Reference: {{reference}}\n"
            "Form: {{form_title}}\n"
            "Organization: {{entity_name}}\n\n"
            "You can follow progress here:\n{{track_url}}\n\n"
            "Thank you."
        ),
    ),
    EntityEmailNotificationTemplate.Kind.ACCEPTED: (
        _("Your submission to {{form_title}} was accepted"),
        _(
            "Hello,\n\n"
            "Your submission has been accepted and the workflow is complete.\n\n"
            "Reference: {{reference}}\n"
            "Form: {{form_title}}\n\n"
            "View details:\n{{track_url}}\n\n"
            "Thank you."
        ),
    ),
    EntityEmailNotificationTemplate.Kind.REJECTED: (
        _("Update on your submission to {{form_title}}"),
        _(
            "Hello,\n\n"
            "Your submission was not approved.\n\n"
            "Reference: {{reference}}\n"
            "Form: {{form_title}}\n"
            "Reason: {{decision_comment}}\n\n"
            "View details:\n{{track_url}}\n\n"
            "Thank you."
        ),
    ),
    EntityEmailNotificationTemplate.Kind.STAFF_CONTACT: (
        _("Message about your submission {{reference}}"),
        _(
            "Hello,\n\n"
            "Regarding your submission to {{form_title}} (reference {{reference}}).\n\n"
            "(Add your message here before sending.)\n\n"
            "Thank you."
        ),
    ),
}


def _placeholder_pattern() -> re.Pattern[str]:
    return re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render_notification_template(text: str, context: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return context.get(key, "")

    return _placeholder_pattern().sub(repl, text or "")


def submission_track_url(submission: FormSubmission, request=None) -> str:
    from .subdomain import portal_absolute_uri

    form = submission.form
    entity = form.entity
    return portal_absolute_uri(
        request,
        "magicforms:submission_detail",
        entity=entity,
        entity_slug=entity.slug,
        slug=form.slug,
        token=submission.reference_token,
    )


def build_notification_context(
    submission: FormSubmission,
    *,
    request=None,
    event: SubmissionEvent | None = None,
    workflow_decision_comment: str = "",
    staff_user=None,
) -> dict[str, str]:
    form = submission.form
    entity = form.entity
    email, _src, _lbl = default_applicant_email(submission)
    step_label = ""
    if submission.current_step_id and submission.current_step:
        step_label = submission.current_step.label
    comment = (workflow_decision_comment or "").strip()
    if not comment and event:
        msg = (event.message or "")
        if "Comment:" in msg:
            comment = msg.split("Comment:", 1)[-1].strip()
    staff_name = ""
    if staff_user is not None:
        staff_name = (staff_user.get_full_name() or "").strip() or staff_user.get_username()
    submitted_at = ""
    if submission.submitted_at:
        submitted_at = date_format(
            timezone.localtime(submission.submitted_at),
            format="SHORT_DATETIME_FORMAT",
        )
    return {
        "form_title": form.title,
        "entity_name": entity.name,
        "reference": str(submission.reference_token),
        "submitted_at": submitted_at,
        "applicant_email": email,
        "workflow_state": str(submission.get_workflow_state_display()),
        "current_step": step_label,
        "decision_comment": comment,
        "track_url": submission_track_url(submission, request),
        "staff_name": staff_name,
    }


def ensure_entity_notification_defaults(entity: Entity) -> None:
    """Create behavior row and default templates for an organization."""
    EntityEmailNotificationBehavior.objects.get_or_create(entity=entity)
    for kind, (subj, body) in _DEFAULT_COPY.items():
        EntityEmailNotificationTemplate.objects.get_or_create(
            entity=entity,
            kind=kind,
            defaults={
                "subject": str(subj)[: EntityEmailNotificationTemplate.MAX_SUBJECT_LEN],
                "body": str(body)[: EntityEmailNotificationTemplate.MAX_BODY_LEN],
                "is_active": True,
            },
        )


def get_notification_behavior(entity: Entity) -> EntityEmailNotificationBehavior:
    ensure_entity_notification_defaults(entity)
    return entity.email_notification_behavior


def get_notification_template(
    entity: Entity, kind: str
) -> EntityEmailNotificationTemplate | None:
    ensure_entity_notification_defaults(entity)
    return EntityEmailNotificationTemplate.objects.filter(entity=entity, kind=kind).first()


def _behavior_allows(behavior: EntityEmailNotificationBehavior, template_kind: str, event_kind: str) -> bool:
    if template_kind == EntityEmailNotificationTemplate.Kind.SUBMITTED:
        return behavior.notify_on_submit
    if template_kind == EntityEmailNotificationTemplate.Kind.REJECTED:
        return behavior.notify_on_reject
    if template_kind == EntityEmailNotificationTemplate.Kind.ACCEPTED:
        if event_kind == SubmissionEvent.Kind.STEP_APPROVED:
            return behavior.notify_on_step_approved
        return behavior.notify_on_accept
    return False


def resolve_notification_recipient(submission: FormSubmission) -> str:
    candidates = applicant_email_candidates(submission)
    return candidates[0][0] if candidates else ""


def dispatch_notification_email_for_event(
    submission: FormSubmission,
    event: SubmissionEvent,
    *,
    request=None,
    workflow_decision: str = "",
    workflow_decision_comment: str = "",
    staff_user=None,
) -> bool:
    """
    Send applicant email for a timeline event when enabled. Returns True if sent.
    """
    entity = submission.form.entity
    if not entity_notifications_may_send(entity):
        return False

    template_kind = _EVENT_TO_TEMPLATE_KIND.get(event.kind)
    if not template_kind:
        return False

    behavior = get_notification_behavior(entity)
    if not _behavior_allows(behavior, template_kind, event.kind):
        return False

    if event.kind == SubmissionEvent.Kind.STEP_APPROVED:
        template_kind = EntityEmailNotificationTemplate.Kind.ACCEPTED

    tpl = get_notification_template(entity, template_kind)
    if not tpl or not tpl.is_active:
        return False

    to_addr = resolve_notification_recipient(submission)
    if not to_addr:
        logger.info(
            "Skip notification email (no applicant address) submission=%s event=%s",
            submission.pk,
            event.kind,
        )
        return False

    comment = (workflow_decision_comment or "").strip()
    if event.kind == SubmissionEvent.Kind.WORKFLOW_REJECTED and not comment:
        comment = (workflow_decision or "").strip()

    ctx = build_notification_context(
        submission,
        request=request,
        event=event,
        workflow_decision_comment=comment,
        staff_user=staff_user,
    )
    subject = render_notification_template(tpl.subject, ctx)[: EntityEmailNotificationTemplate.MAX_SUBJECT_LEN]
    body = render_notification_template(tpl.body, ctx)[: EntityEmailNotificationTemplate.MAX_BODY_LEN]

    try:
        send_organization_email(entity, to=to_addr, subject=subject, body=body)
    except Exception:
        logger.exception(
            "Notification email failed submission=%s kind=%s",
            submission.pk,
            template_kind,
        )
        return False
    return True


def staff_contact_email_defaults(
    submission: FormSubmission,
    *,
    request=None,
    staff_user=None,
) -> tuple[str, str]:
    """Prefill subject/body for manual “Email applicant” from staff_contact template."""
    entity = submission.form.entity
    behavior = get_notification_behavior(entity)
    if not behavior.staff_contact_use_template:
        from .submission_applicant_email import default_applicant_email_subject

        return default_applicant_email_subject(submission), ""

    tpl = get_notification_template(entity, EntityEmailNotificationTemplate.Kind.STAFF_CONTACT)
    if not tpl or not tpl.is_active:
        from .submission_applicant_email import default_applicant_email_subject

        return default_applicant_email_subject(submission), ""

    ctx = build_notification_context(submission, request=request, staff_user=staff_user)
    return (
        render_notification_template(tpl.subject, ctx)[: EntityEmailNotificationTemplate.MAX_SUBJECT_LEN],
        render_notification_template(tpl.body, ctx)[: EntityEmailNotificationTemplate.MAX_BODY_LEN],
    )


def _applicant_chat_staff_recipients(submission: FormSubmission) -> list[str]:
    """
    Staff addresses to notify when the applicant replies: current step assignees,
    then staff who already wrote in this chat, then the form creator.
    """
    seen: set[str] = set()
    out: list[str] = []

    def add(user) -> None:
        addr = (getattr(user, "email", "") or "").strip()
        key = addr.casefold()
        if not addr or key in seen:
            return
        seen.add(key)
        out.append(addr)

    if submission.current_step_id and submission.current_step:
        for u in submission.current_step.assigned_users.all():
            add(u)
    for msg in submission.applicant_messages.filter(
        is_from_applicant=False, author__isnull=False
    ).select_related("author"):
        add(msg.author)
    if getattr(submission.form, "created_by", None):
        add(submission.form.created_by)
    return out


def dispatch_applicant_chat_email(
    submission: FormSubmission,
    chat_message,
    *,
    request=None,
) -> None:
    """
    On commit: email notification for one applicant-chat message.
    Staff message → applicant (with track link); applicant reply → staff (with manage link).
    """
    entity = submission.form.entity
    ref = str(submission.reference_token)
    body_text = (chat_message.body or "").strip()

    def _run():
        try:
            if chat_message.is_from_applicant:
                recipients = _applicant_chat_staff_recipients(submission)
                if not recipients:
                    logger.info(
                        "Skip applicant chat staff email (no recipients) submission=%s",
                        submission.pk,
                    )
                    return
                manage_path = reverse(
                    "manage:submission_manage_detail",
                    kwargs={"pk": submission.form_id, "submission_id": submission.pk},
                )
                manage_url = (
                    request.build_absolute_uri(manage_path) if request else manage_path
                )
                subject = _("Applicant replied — %(form)s (%(ref)s)") % {
                    "form": submission.form.title,
                    "ref": ref[:8],
                }
                body = _(
                    "The applicant sent a new message on submission %(ref)s "
                    "(%(form)s):\n\n%(message)s\n\nReply from the submission page:\n%(url)s"
                ) % {
                    "ref": ref,
                    "form": submission.form.title,
                    "message": body_text,
                    "url": manage_url,
                }
                for addr in recipients:
                    send_organization_email(entity, to=addr, subject=subject, body=body)
            else:
                if not entity_notifications_may_send(entity):
                    return
                to_addr = resolve_notification_recipient(submission)
                if not to_addr:
                    logger.info(
                        "Skip applicant chat email (no applicant address) submission=%s",
                        submission.pk,
                    )
                    return
                staff_name = ""
                if chat_message.author_id and chat_message.author:
                    staff_name = (
                        chat_message.author.get_full_name() or ""
                    ).strip() or chat_message.author.get_username()
                subject = _("New message about your submission %(ref)s") % {"ref": ref[:8]}
                body = _(
                    "Hello,\n\n"
                    "You have a new message about your submission to %(form)s "
                    "(reference %(ref)s)%(from_part)s:\n\n%(message)s\n\n"
                    "Read and reply on your track page:\n%(url)s\n\n"
                    "Thank you."
                ) % {
                    "form": submission.form.title,
                    "ref": ref,
                    "from_part": (" " + str(_("from %(name)s") % {"name": staff_name}))
                    if staff_name
                    else "",
                    "message": body_text,
                    "url": submission_track_url(submission, request),
                }
                send_organization_email(entity, to=to_addr, subject=subject, body=body)
        except Exception:
            logger.exception(
                "Applicant chat notification email failed submission=%s message=%s",
                submission.pk,
                chat_message.pk,
            )

    transaction.on_commit(_run)


def queue_after_submission_event(
    submission: FormSubmission,
    event: SubmissionEvent,
    *,
    request=None,
    workflow_decision: str = "",
    workflow_decision_comment: str = "",
    staff_user=None,
) -> None:
    """On commit: outbound API hook + applicant notification email."""

    def _run():
        from .outbound.dispatch import dispatch_outbound_for_event

        dispatch_outbound_for_event(
            submission,
            event,
            workflow_decision=workflow_decision,
            workflow_decision_comment=workflow_decision_comment,
        )
        dispatch_notification_email_for_event(
            submission,
            event,
            request=request,
            workflow_decision=workflow_decision,
            workflow_decision_comment=workflow_decision_comment,
            staff_user=staff_user,
        )

    transaction.on_commit(_run)
