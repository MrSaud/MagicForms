"""Display-time translation for submission timeline (UI + PDF)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from .i18n_db import gettext_db
from .models import SubmissionEvent

if TYPE_CHECKING:
    from .models import SubmissionEvent as SubmissionEventT

_COMMENT_MARKER = "\n\nComment: "
_DELEGATE_FOR_RE = re.compile(r"\s*\[delegate for:\s*(.+?)\]\s*$", re.I)
_DELEGATE_BARE_RE = re.compile(r"\s*\[delegate\]\s*$", re.I)

_APPROVED_ADVANCED_RE = re.compile(r'^Approved; advanced to "(.+)"\.\s*$')
_RELATED_AVAILABLE_RE = re.compile(
    r'^Related form available: "(.+)"\.\s*Complete it using the link in the related forms section below\.\s*$',
    re.I,
)
_RELATED_SUBMITTED_RE = re.compile(r'^Related form submitted: "(.+)"\.\s*$', re.I)
_DOC_ADDED_RE = re.compile(r"^Document added: (.+)$", re.I)
_DOC_ADDED_MANAGE_RE = re.compile(r"^Document added \(manage\): (.+)$", re.I)
_DOC_ADDED_TITLE_RE = re.compile(r"^Document added: (.+) — (.+)$", re.I)
_DOC_ADDED_MANAGE_TITLE_RE = re.compile(r"^Document added \(manage\): (.+) — (.+)$", re.I)
_FORWARDED_RE = re.compile(
    r"^Forwarded to (\S+)(?: \((.+)\))?(?:\nNote: (.+))?$",
    re.S,
)
_ATT_REMOVED_RE = re.compile(r"^Attachment removed: (.+)$", re.I)
_ATT_REMOVED_MANAGE_RE = re.compile(r"^Attachment removed \(manage\): (.+)$", re.I)
_EMAIL_APPLICANT_RE = re.compile(r"^Email sent to applicant \((.+)\): (.+)$", re.I)
_UNDO_MINUTES_RE = re.compile(
    r"^Approval undone \(within (\d+) minutes\)\. Workflow position reverted\.\s*$",
    re.I,
)


def timeline_event_kind_label(event: SubmissionEventT) -> str:
    """Kind title for timeline UI/PDF (distinct from grid column ``Submitted``)."""
    kind = event.kind
    labels = {
        SubmissionEvent.Kind.SUBMITTED: pgettext("timeline event", "Submitted"),
        SubmissionEvent.Kind.STEP_CHANGED: pgettext("timeline event", "Workflow step changed"),
        SubmissionEvent.Kind.NOTE: pgettext("timeline event", "Note"),
        SubmissionEvent.Kind.STEP_APPROVED: pgettext("timeline event", "Step approved"),
        SubmissionEvent.Kind.WORKFLOW_COMPLETED: pgettext("timeline event", "Workflow completed"),
        SubmissionEvent.Kind.APPROVE_UNDONE: pgettext("timeline event", "Approval undone"),
        SubmissionEvent.Kind.WORKFLOW_REJECTED: pgettext("timeline event", "Workflow rejected"),
        SubmissionEvent.Kind.ROUTED: pgettext("timeline event", "Routed"),
        SubmissionEvent.Kind.ATTACHMENT_ADDED: pgettext("timeline event", "Document attached"),
        SubmissionEvent.Kind.FORWARDED: pgettext("timeline event", "Forwarded"),
        SubmissionEvent.Kind.SUPPLEMENTARY_INVITED: pgettext("timeline event", "Related form available"),
        SubmissionEvent.Kind.SUPPLEMENTARY_SUBMITTED: pgettext(
            "timeline event", "Related form submitted"
        ),
    }
    label = labels.get(kind)
    if label is not None:
        return str(label)
    return gettext_db(str(event.get_kind_display()))


def timeline_event_step_label(step) -> str:
    if step is None:
        return ""
    return gettext_db(str(step.label))


def _split_timeline_message(raw: str) -> tuple[str, str, str]:
    """Return ``(core, comment, delegate_suffix)``."""
    msg = (raw or "").replace("\r\n", "\n").strip()
    if not msg:
        return "", "", ""

    comment = ""
    if _COMMENT_MARKER in msg:
        base, comment = msg.split(_COMMENT_MARKER, 1)
        core = base.rstrip("\n")
        comment = comment.strip()
    else:
        core = msg

    delegate = ""
    m = _DELEGATE_FOR_RE.search(core)
    if m:
        delegate = m.group(0)
        core = core[: m.start()].rstrip()
    elif _DELEGATE_BARE_RE.search(core):
        delegate = " [delegate]"
        core = _DELEGATE_BARE_RE.sub("", core).rstrip()

    return core.strip(), comment, delegate


def _translate_delegate_suffix(suffix: str) -> str:
    if not suffix:
        return ""
    m = re.match(r"\s*\[delegate for:\s*(.+?)\]\s*$", suffix, re.I)
    if m:
        names = m.group(1).strip()
        return str(pgettext("timeline delegate", " [delegate for: %(names)s]") % {"names": names})
    if suffix.strip().lower() == "[delegate]":
        return str(pgettext("timeline delegate", " [delegate]"))
    return suffix


def _translate_timeline_message_core(core: str, *, step_label: str | None = None) -> str:
    if not core:
        return ""

    if core == "Form submitted.":
        return str(_("Form submitted."))
    if core == "Workflow rejected; stopped at this step.":
        return str(_("Workflow rejected; stopped at this step."))
    if core == "All workflow steps approved; submission complete.":
        return str(_("All workflow steps approved; submission complete."))

    m = _UNDO_MINUTES_RE.match(core)
    if m:
        minutes = int(m.group(1))
        return str(
            _("Approval undone (within %(minutes)d minutes). Workflow position reverted.")
            % {"minutes": minutes}
        )

    m = _APPROVED_ADVANCED_RE.match(core)
    if m:
        step_name = m.group(1)
        display = gettext_db(step_label) if step_label else gettext_db(step_name)
        return str(_('Approved; advanced to "%(step)s".') % {"step": display})

    m = _RELATED_AVAILABLE_RE.match(core)
    if m:
        title = gettext_db(m.group(1))
        return str(
            _(
                'Related form available: "%(title)s". '
                "Complete it using the link in the related forms section below."
            )
            % {"title": title}
        )

    m = _RELATED_SUBMITTED_RE.match(core)
    if m:
        title = gettext_db(m.group(1))
        return str(_('Related form submitted: "%(title)s".') % {"title": title})

    for pattern, manage in (
        (_DOC_ADDED_MANAGE_TITLE_RE, True),
        (_DOC_ADDED_TITLE_RE, False),
        (_DOC_ADDED_MANAGE_RE, True),
        (_DOC_ADDED_RE, False),
    ):
        m = pattern.match(core)
        if m:
            if len(m.groups()) == 2:
                fname, title = m.group(1), m.group(2)
                if manage:
                    return str(_("Document added (manage): %(file)s — %(title)s") % {"file": fname, "title": title})
                return str(_("Document added: %(file)s — %(title)s") % {"file": fname, "title": title})
            fname = m.group(1)
            if manage:
                return str(_("Document added (manage): %(file)s") % {"file": fname})
            return str(_("Document added: %(file)s") % {"file": fname})

    m = _ATT_REMOVED_MANAGE_RE.match(core)
    if m:
        return str(_("Attachment removed (manage): %(name)s") % {"name": m.group(1)})
    m = _ATT_REMOVED_RE.match(core)
    if m:
        return str(_("Attachment removed: %(name)s") % {"name": m.group(1)})
    m = _EMAIL_APPLICANT_RE.match(core)
    if m:
        return str(_("Email sent to applicant (%(addr)s): %(subject)s") % {"addr": m.group(1), "subject": m.group(2)})

    m = _FORWARDED_RE.match(core)
    if m:
        username, full_name, note = m.group(1), m.group(2), m.group(3)
        if full_name and note:
            return str(
                _("Forwarded to %(user)s (%(name)s)\nNote: %(note)s")
                % {"user": username, "name": full_name.strip(), "note": note.strip()}
            )
        if full_name:
            return str(_("Forwarded to %(user)s (%(name)s)") % {"user": username, "name": full_name.strip()})
        if note:
            return str(_("Forwarded to %(user)s\nNote: %(note)s") % {"user": username, "note": note.strip()})
        return str(_("Forwarded to %(user)s") % {"user": username})

    # Messages stored via gettext at creation time (email, attachment removal, etc.).
    translated = gettext_db(core)
    if translated != core:
        return translated
    catalog = _(core)
    if catalog != core:
        return str(catalog)
    return core


def timeline_event_message_display(
    message: str | None,
    *,
    step_label: str | None = None,
) -> str:
    """Translate stored timeline event message for the active locale."""
    core, comment, delegate = _split_timeline_message(message or "")
    if not core and not comment and not delegate:
        return ""

    parts: list[str] = []
    if core:
        parts.append(_translate_timeline_message_core(core, step_label=step_label))
    if comment:
        parts.append(f"{_('Comment:')} {comment}")
    text = "\n\n".join(parts) if len(parts) > 1 else (parts[0] if parts else "")
    if delegate:
        text = (text + _translate_delegate_suffix(delegate)).strip()
    return text.replace("\r\n", "\n")
