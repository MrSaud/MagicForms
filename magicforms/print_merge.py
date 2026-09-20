"""
Merge submission answers into staff-uploaded print templates: primary **DOCX or PDF**, optional **ODT**
for download/editing (answers are not merged into ODT).

DOCX: use Word + ``docxtpl`` Jinja placeholders matching each field's internal ``name``
(use letters, numbers, underscores — hyphens become underscores in the template context).

PDF: fillable AcroForm. Field names usually match each field's internal ``name`` (slug). Many tools
produce **hierarchical** names (for example ``topmostSubform[0].subform.field_name``): MagicForms fills
those by resolving the trailing segment against your slug and Jinja-safe key. Some PDFs store the
field tag ``/T`` as a PDF **name** (``/fullname``) rather than a plain string; those are matched too.

Field names that start with a digit (``1-copy``) are also exposed with an ``f_`` prefix
(``{{ f_1_copy }}``) because Jinja identifiers cannot begin with a digit.

Also available in templates: ``form_title``, ``form_description``, ``submitter_email``,
``reference_token``, ``submitted_at``, ``current_step_label``,
``workflow_timeline``, ``workflow_actions_summary``, ``workflow_comments``,
``workflow_last_action``, ``workflow_last_comment`` (strings).

DOCX only (for ``InlineImage``): ``signature_primary`` / ``submission_signatures`` (respondent; primary is the image marked primary on the signatures page — first ``sort_order``).
When no image is stored, ``signature_primary`` is the submit date as plain text (use ``{{ signature_primary }}`` in Word).
``signature_primary_date`` / ``approver_signature_primary_date`` are always set (same dates) for a second line under an image.
``approver_signature_primary`` / ``approver_signatures`` (staff who approved). Without an image, the primary placeholder is the approval date only. Put ``{{ approver_signature_primary_on_behalf }}`` below for delegation text when applicable.
PDF AcroForm fields are text-only; use ``workflow_*`` and ``workflow_approver_signatures`` there.
PDF generated from a DOCX
template (via LibreOffice) includes embedded signature images like the DOCX.

Optional **ODT** (`Form.print_template_odt`) is returned unchanged for download (no answer merge).
PDF from ODT-only setups uses LibreOffice on that file when configured.

Merged **DOCX** can be marked read-only in Word (``MAGIFORM_DOCX_MERGE_READ_ONLY``); that is not cryptographic protection — use **PDF** when you need a format that is not meaningfully editable in Word.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any, cast

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django.utils import translation
from django.utils.translation import gettext as _

from .models import FieldType, Form, FormSubmission, SubmissionEvent, WorkflowDelegation
from .pdf_branding import stamp_entity_logo_on_pdf

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_SETTINGS_XML_PATH = "word/settings.xml"


def _w_qn(local: str) -> str:
    return f"{{{_W_NS}}}{local}"


def _patch_word_settings_read_only(xml_bytes: bytes) -> bytes:
    """
    Insert ``readOnlyRecommended`` and enforced ``documentProtection`` (readOnly) into ``settings.xml``.

    Microsoft Word honors these for typical users; other editors may ignore them. This is not a substitute
    for PDF or rights-managed encryption.
    """
    ET.register_namespace("w", _W_NS)
    root = ET.fromstring(xml_bytes)
    for child in list(root):
        if child.tag == _w_qn("documentProtection"):
            root.remove(child)
    prot = ET.SubElement(root, _w_qn("documentProtection"))
    prot.set(_w_qn("edit"), "readOnly")
    prot.set(_w_qn("enforcement"), "1")
    if not any(ch.tag == _w_qn("readOnlyRecommended") for ch in root):
        ET.SubElement(root, _w_qn("readOnlyRecommended"))
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def _rewrite_docx_package(docx_bytes: bytes, *, read_only_marks: bool) -> bytes:
    """
    Re-pack the DOCX zip, dropping duplicate entry names (last occurrence wins) and optionally
    patching ``settings.xml`` so Word opens the file as read-only.

    python-docx / docxtpl can emit ``docProps/core.xml`` twice for some templates. Word tolerates
    that, but LibreOffice refuses to load a zip with duplicate names ("source file could not be
    loaded"), which broke DOCX → PDF conversion.
    """
    in_buf = BytesIO(docx_bytes)
    out_buf = BytesIO()
    with zipfile.ZipFile(in_buf, "r") as zin:
        entries: dict[str, tuple[zipfile.ZipInfo, bytes]] = {}
        for info in zin.infolist():
            entries[info.filename] = (info, zin.read(info))
        with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, (info, data) in entries.items():
                if read_only_marks and name == _SETTINGS_XML_PATH:
                    data = _patch_word_settings_read_only(data)
                zout.writestr(info, data)
    return out_buf.getvalue()


def _apply_docx_read_only_marks(docx_bytes: bytes) -> bytes:
    """Rewrite the DOCX package so Word opens merged output as read-only / restrict editing."""
    return _rewrite_docx_package(docx_bytes, read_only_marks=True)


class PrintMergeError(Exception):
    """User-facing error when a document cannot be generated."""


def _jinja_safe_key(name: str) -> str:
    """Jinja2 variables cannot contain ``-``; map to ``_``."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", (name or "").strip()) or "field"


def _workflow_event_action_label(kind: str) -> str:
    mapping = {
        "submitted": "Submitted",
        "step_changed": "Step changed",
        "note": "Note",
        "step_approved": "Approved (next step)",
        "workflow_completed": "Approved (completed)",
        "approve_undone": "Approval undone",
        "workflow_rejected": "Rejected",
        "attachment_added": "Document attached",
        "forwarded": "Forwarded",
        "supplementary_invited": "Related form available",
        "supplementary_submitted": "Related form submitted",
    }
    return mapping.get(kind, kind)


def _workflow_timeline_text(submission: FormSubmission) -> str:
    lines: list[str] = []
    events = submission.events.select_related("step", "created_by").order_by("created_at")
    for ev in events:
        ts = timezone.localtime(ev.created_at).strftime("%Y-%m-%d %H:%M")
        actor = ev.created_by.get_username() if ev.created_by else "—"
        action = _workflow_event_action_label(ev.kind)
        step = ev.step.label if ev.step_id else ""
        head = f"{ts} · {action} · {actor}"
        if step:
            head += f" · {step}"
        lines.append(head)
        msg = (ev.message or "").strip()
        if msg:
            for part in msg.splitlines():
                lines.append(f"    {part}")
    return "\n".join(lines)


def _workflow_actions_summary(submission: FormSubmission) -> str:
    """Short line of approve/reject/complete style actions for PDF single-line fields."""
    parts: list[str] = []
    for ev in submission.events.select_related("created_by").order_by("created_at"):
        if ev.kind not in ("step_approved", "workflow_completed", "workflow_rejected", "approve_undone"):
            continue
        ts = timezone.localtime(ev.created_at).strftime("%Y-%m-%d %H:%M")
        actor = ev.created_by.get_username() if ev.created_by else "—"
        label = _workflow_event_action_label(ev.kind)
        parts.append(f"{ts} {label} ({actor})")
    return " | ".join(parts)


def _workflow_comments_text(submission: FormSubmission) -> str:
    """All non-empty event messages (includes approve/reject comments)."""
    blocks: list[str] = []
    for ev in submission.events.order_by("created_at"):
        msg = (ev.message or "").strip()
        if msg:
            blocks.append(msg)
    return "\n\n".join(blocks)


def _user_display_name(user) -> str:
    full = (user.get_full_name() or "").strip()
    if full:
        return full
    return (user.get_username() or "").strip()


def _merge_datetime_local(dt) -> str:
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M")


def _bilingual_date_line(msgid: str, dt) -> str:
    """English + Arabic lines for the same ``msgid`` (compile ``-l ar``)."""
    date_s = _merge_datetime_local(dt)
    en = _(msgid) % {"date": date_s}
    with translation.override("ar"):
        ar = _(msgid) % {"date": date_s}
    return f"{en}\n{ar}"


def _delegation_on_behalf_lines(actor, step, entity_id: int, when) -> str:
    """Bilingual “on behalf of … · date” when ``actor`` approved as an active delegate."""
    if not actor or not step or not entity_id:
        return ""
    assignee_ids = set(step.assigned_users.values_list("pk", flat=True))
    if actor.pk in assignee_ids:
        return ""
    on_date = timezone.localdate(when) if when else timezone.localdate()
    delegator_ids = set(
        WorkflowDelegation.objects.filter(
            delegate=actor,
            entity_id=entity_id,
            is_active=True,
        )
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=on_date))
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on_date))
        .values_list("delegator_id", flat=True)
    )
    covered = assignee_ids & delegator_ids
    if not covered:
        return ""
    User = get_user_model()
    blocks: list[str] = []
    date_s = _merge_datetime_local(when) if when else ""
    for delegator in User.objects.filter(pk__in=covered).order_by("username")[:5]:
        name = _user_display_name(delegator)
        en = _("On behalf of %(name)s · %(date)s") % {"name": name, "date": date_s}
        with translation.override("ar"):
            ar = _("On behalf of %(name)s · %(date)s") % {"name": name, "date": date_s}
        blocks.append(f"{en}\n{ar}")
    return "\n".join(blocks)


def _signature_date_fallback_plain(dt) -> str:
    """Plain date/time for signature placeholders when no image is on file."""
    if not dt:
        return ""
    return _merge_datetime_local(dt)


def _applicant_signature_fallback_plain(submission: FormSubmission) -> str:
    """Submit datetime only when the respondent has no signature image."""
    return _signature_date_fallback_plain(submission.submitted_at)


def _approver_signature_fallback_plain(ev: SubmissionEvent) -> str:
    """Approval datetime only when the approver has no signature image."""
    return _signature_date_fallback_plain(ev.created_at)


def _approver_on_behalf_for_event(ev: SubmissionEvent, submission: FormSubmission) -> str:
    """Bilingual on-behalf block when the approver acted as a delegate (empty otherwise)."""
    if not ev.created_by:
        return ""
    return _delegation_on_behalf_lines(
        ev.created_by,
        ev.step,
        submission.form.entity_id,
        ev.created_at,
    )


def _approver_on_behalf_docx(ev: SubmissionEvent, submission: FormSubmission):
    """Small RichText on-behalf lines for DOCX under a signature image."""
    plain = _approver_on_behalf_for_event(ev, submission)
    if not plain:
        return ""
    try:
        from docxtpl import RichText
    except ImportError as exc:
        raise PrintMergeError("docxtpl is not installed.") from exc

    rt = RichText()
    for i, line in enumerate(plain.split("\n")):
        if not line.strip():
            continue
        if i:
            rt.add("\n")
        rt.add(line, size=14)
    return rt


def _approver_signature_fallback_text(ev: SubmissionEvent, submission: FormSubmission) -> str:
    """Plain approval date for PDF / ``fallback_plain`` (delegation uses ``on_behalf`` placeholders)."""
    del submission
    return _approver_signature_fallback_plain(ev)


def _workflow_approver_signature_note(submission: FormSubmission) -> str:
    """Multiline text for PDF fields: approver lines (image on file, or name/date/delegation fallback)."""
    lines: list[str] = []
    for ev in (
        submission.events.filter(
            kind__in=(
                SubmissionEvent.Kind.STEP_APPROVED,
                SubmissionEvent.Kind.WORKFLOW_COMPLETED,
            ),
            created_by__isnull=False,
        )
        .select_related("created_by", "step")
        .prefetch_related("created_by__signatures", "step__assigned_users")
        .order_by("created_at")
    ):
        if ev.created_by.signatures.exists():
            ts = _merge_datetime_local(ev.created_at)
            actor = ev.created_by.get_username()
            step = ev.step.label if ev.step_id else ""
            if step:
                line = f"{ts} · {step} · {actor} ({_('signature on file')})"
            else:
                line = f"{ts} · {actor} ({_('signature on file')})"
            behalf = _approver_on_behalf_for_event(ev, submission)
            if behalf:
                line = f"{line} · {behalf.replace(chr(10), ' / ')}"
            lines.append(line)
        else:
            block = _approver_signature_fallback_plain(ev)
            if block:
                lines.append(block)
    return "\n".join(lines)


def _workflow_last_action_and_comment(submission: FormSubmission) -> tuple[str, str]:
    """Most recent approve/reject/complete line, and most recent non-empty event message."""
    last_action = ""
    for ev in submission.events.select_related("created_by").order_by("-created_at"):
        if ev.kind in ("step_approved", "workflow_completed", "workflow_rejected", "approve_undone"):
            actor = ev.created_by.get_username() if ev.created_by else "—"
            ts = timezone.localtime(ev.created_at).strftime("%Y-%m-%d %H:%M")
            last_action = f"{_workflow_event_action_label(ev.kind)} · {actor} · {ts}"
            break
    last_comment = ""
    for ev in submission.events.order_by("-created_at"):
        if (ev.message or "").strip():
            last_comment = (ev.message or "").strip()
            break
    return last_action, last_comment


def _display_value(field, sv) -> str:
    if sv is None:
        return ""
    raw = sv.value or ""
    ft = field.field_type
    if ft == FieldType.CHECKBOX:
        return "Yes" if raw == "yes" else "No"
    if ft == FieldType.CHECKLIST:
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        return "; ".join(lines)
    if ft == FieldType.FILE:
        if sv.attachment:
            return os.path.basename(sv.attachment.name)
        return raw or ""
    return raw


def build_print_context(submission: FormSubmission) -> dict[str, Any]:
    """Flat string context for PDF AcroForm and base strings for DOCX (before inline images)."""
    form = submission.form
    by_field_id = {v.field_id: v for v in submission.values.all()}
    last_action, last_comment = _workflow_last_action_and_comment(submission)
    ctx: dict[str, Any] = {
        "form_title": form.title,
        "form_description": form.description or "",
        "submitter_email": submission.submitter_email or "",
        "reference_token": str(submission.reference_token),
        "submitted_at": timezone.localtime(submission.submitted_at).strftime("%Y-%m-%d %H:%M"),
        "current_step_label": submission.get_print_current_step_label(),
        "workflow_timeline": _workflow_timeline_text(submission),
        "workflow_actions_summary": _workflow_actions_summary(submission),
        "workflow_comments": _workflow_comments_text(submission),
        "workflow_last_action": last_action,
        "workflow_last_comment": last_comment,
        "workflow_approver_signatures": _workflow_approver_signature_note(submission),
    }
    for ff in form.get_ordered_fields():
        sv = by_field_id.get(ff.pk)
        text = _display_value(ff, sv)
        key = ff.name
        ctx[key] = text
        jk = _jinja_safe_key(ff.name)
        if jk != key:
            ctx[jk] = text
        if jk[:1].isdigit():
            # Jinja identifiers cannot start with a digit; expose ``f_<key>`` for such field names.
            ctx["f_" + jk] = text
    for k, v in list(ctx.items()):
        if isinstance(v, str):
            ctx[k] = v
        else:
            ctx[k] = str(v)
    return ctx


def _inject_docx_signature_images(doc: Any, ctx: dict[str, Any], submission: FormSubmission) -> None:
    """Add ``submission_signatures`` and ``signature_primary`` (image or name/date fallback) for docxtpl."""
    try:
        from docxtpl import InlineImage
        from docx.shared import Mm
    except ImportError as exc:
        raise PrintMergeError("docxtpl is not installed.") from exc

    fallback_plain = _applicant_signature_fallback_plain(submission)
    ctx["signature_primary_fallback"] = fallback_plain
    ctx["signature_primary_date"] = fallback_plain
    ctx["signature_primary_has_image"] = False

    user = submission.submitted_by
    rows: list[dict[str, Any]] = []
    if not user:
        ctx["submission_signatures"] = []
        ctx["signature_primary"] = fallback_plain
        return

    width = Mm(42)
    for sig in list(user.signatures.order_by("sort_order", "id"))[:20]:
        if not sig.image:
            continue
        img_arg: Any
        try:
            p = sig.image.path
            if os.path.isfile(p):
                img_arg = p
            else:
                raise FileNotFoundError
        except (NotImplementedError, ValueError, FileNotFoundError, AttributeError):
            buf = BytesIO()
            sig.image.open("rb")
            try:
                buf.write(sig.image.read())
            finally:
                sig.image.close()
            buf.seek(0)
            img_arg = buf
        try:
            rows.append(
                {
                    "label": sig.label or "",
                    "image": InlineImage(doc, img_arg, width=width),
                    "fallback": "",
                }
            )
        except Exception:
            continue

    ctx["submission_signatures"] = rows
    if rows:
        ctx["signature_primary"] = rows[0]["image"]
        ctx["signature_primary_has_image"] = True
    else:
        ctx["signature_primary"] = fallback_plain


def _inject_docx_approver_signature_images(doc: Any, ctx: dict[str, Any], submission: FormSubmission) -> None:
    """DOCX: ``approver_signatures`` / ``approver_signature_primary`` (image or small approval date fallback)."""
    try:
        from docxtpl import InlineImage
        from docx.shared import Mm
    except ImportError as exc:
        raise PrintMergeError("docxtpl is not installed.") from exc

    width = Mm(42)
    rows: list[dict[str, Any]] = []
    for ev in (
        submission.events.filter(
            kind__in=(
                SubmissionEvent.Kind.STEP_APPROVED,
                SubmissionEvent.Kind.WORKFLOW_COMPLETED,
            ),
            created_by__isnull=False,
        )
        .select_related("created_by", "step")
        .prefetch_related("step__assigned_users")
        .order_by("created_at")
    ):
        user = ev.created_by
        parts: list[str] = []
        if ev.step_id and ev.step:
            parts.append(ev.step.label)
        parts.append(_user_display_name(user))
        label = " · ".join(parts)
        fallback_plain = _approver_signature_fallback_plain(ev)
        on_behalf = _approver_on_behalf_for_event(ev, submission)
        on_behalf_docx = _approver_on_behalf_docx(ev, submission)
        image: Any = ""
        sig = user.signatures.order_by("sort_order", "id").first()
        if sig and sig.image:
            img_arg: Any
            try:
                p = sig.image.path
                if os.path.isfile(p):
                    img_arg = p
                else:
                    raise FileNotFoundError
            except (NotImplementedError, ValueError, FileNotFoundError, AttributeError):
                buf = BytesIO()
                sig.image.open("rb")
                try:
                    buf.write(sig.image.read())
                finally:
                    sig.image.close()
                buf.seek(0)
                img_arg = buf
            try:
                image = InlineImage(doc, img_arg, width=width)
            except Exception:
                image = ""
        rows.append(
            {
                "label": label,
                "image": image,
                "fallback": fallback_plain,
                "fallback_plain": fallback_plain,
                "date": fallback_plain,
                "on_behalf": on_behalf,
                "on_behalf_docx": on_behalf_docx,
                "has_image": bool(image),
            }
        )

    ctx["approver_signatures"] = rows
    if rows:
        first = rows[0]
        primary_date = first["date"]
        ctx["approver_signature_primary_date"] = primary_date
        ctx["approver_signature_primary"] = first["image"] if first["has_image"] else primary_date
        ctx["approver_signature_primary_has_image"] = first["has_image"]
        ctx["approver_signature_primary_on_behalf"] = first["on_behalf_docx"] or ""
        ctx["approver_signature_primary_on_behalf_plain"] = first["on_behalf"] or ""
    else:
        ctx["approver_signature_primary"] = ""
        ctx["approver_signature_primary_date"] = ""
        ctx["approver_signature_primary_has_image"] = False
        ctx["approver_signature_primary_on_behalf"] = ""
        ctx["approver_signature_primary_on_behalf_plain"] = ""


def merge_docx(template_bytes: bytes, submission: FormSubmission) -> bytes:
    try:
        from docxtpl import DocxTemplate
    except ImportError as exc:
        raise PrintMergeError("docxtpl is not installed.") from exc

    doc = DocxTemplate(BytesIO(template_bytes))
    ctx = build_print_context(submission)
    _inject_docx_signature_images(doc, ctx, submission)
    _inject_docx_approver_signature_images(doc, ctx, submission)
    try:
        doc.render(ctx)
    except Exception as exc:
        raise PrintMergeError(
            "Could not render the DOCX template. Check Jinja placeholders match your field names."
        ) from exc
    out = BytesIO()
    doc.save(out)
    data = out.getvalue()
    read_only = bool(getattr(settings, "MAGIFORM_DOCX_MERGE_READ_ONLY", True))
    try:
        data = _rewrite_docx_package(data, read_only_marks=read_only)
    except (ET.ParseError, OSError, ValueError, zipfile.BadZipFile):
        # If the package is unusual, return the unmodified merge rather than failing the download.
        pass
    return data


# RHEL/DNF often use /usr/lib64/...; Amazon Linux 2023 official RPMs use /opt/libreoffice*/program/.
_LINUX_SOFFICE_STATIC_PATHS = (
    "/usr/lib64/libreoffice/program/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/usr/lib64/libreoffice/program/soffice.bin",
    "/usr/lib/libreoffice/program/soffice.bin",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/usr/bin/libreoffice",
    "/usr/local/bin/libreoffice",
)


def _normalize_soffice_path(path: str) -> str:
    """
    Prefer ``program/soffice`` over ``soffice.bin``.

    ``soffice.bin`` exits with code 81 on first profile creation; the ``soffice`` launcher
    restarts automatically (see LibreOffice bug #902344 / unoconv #192).
    """
    if not path:
        return path
    if path.endswith("soffice.bin"):
        wrapper = path[: -len(".bin")]
        if os.path.isfile(wrapper):
            return wrapper
    return path


def _discover_linux_soffice_paths() -> list[str]:
    """Versioned installs under ``/opt`` (common on Amazon Linux 2023). Newest first."""
    patterns = (
        "/opt/libreoffice*/program/soffice",
        "/opt/libreoffice*/program/soffice.bin",
        "/usr/local/libreoffice*/program/soffice",
        "/usr/local/libreoffice*/program/soffice.bin",
    )
    by_program_dir: dict[str, str] = {}
    for pattern in patterns:
        for p in glob.glob(pattern):
            prog_dir = os.path.dirname(p)
            existing = by_program_dir.get(prog_dir)
            if existing is None:
                by_program_dir[prog_dir] = p
            elif existing.endswith(".bin") and not p.endswith(".bin"):
                by_program_dir[prog_dir] = p
    found = [_normalize_soffice_path(p) for p in by_program_dir.values()]
    found.sort(reverse=True)
    seen: set[str] = set()
    out: list[str] = []
    for p in found:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

_SOFFICE_RESOLVED: str | None | bool = False  # False = uncached; None = unavailable; str = binary path


def _soffice_candidate_paths() -> list[str]:
    """Paths to try for headless LibreOffice (DOCX/ODT → PDF), expanded from wrappers."""
    seeds: list[str] = []
    for raw in (
        getattr(settings, "MAGIFORM_SOFFICE", None),
        os.environ.get("MAGIFORM_SOFFICE"),
    ):
        if raw is None:
            continue
        s = _normalize_soffice_path(str(raw).strip())
        if s:
            seeds.append(s)
    env_path = _minimal_subprocess_path()
    for cmd in ("soffice", "libreoffice"):
        which = shutil.which(cmd, path=env_path)
        if which:
            seeds.append(which)
    if sys.platform.startswith("linux"):
        seeds.extend(_discover_linux_soffice_paths())
        seeds.extend(_LINUX_SOFFICE_STATIC_PATHS)
    if sys.platform == "darwin":
        seeds.append("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    seen: set[str] = set()
    out: list[str] = []
    for p in seeds:
        for expanded in _expand_soffice_launcher(p):
            if expanded not in seen:
                seen.add(expanded)
                out.append(expanded)
    return _drop_soffice_bin_when_wrapper_exists(out)


def _drop_soffice_bin_when_wrapper_exists(paths: list[str]) -> list[str]:
    """Never use ``soffice.bin`` when ``program/soffice`` exists in the same directory."""
    filtered: list[str] = []
    for p in paths:
        if p.endswith("soffice.bin"):
            wrapper = _normalize_soffice_path(p)
            if wrapper != p and os.path.isfile(wrapper):
                continue
        filtered.append(_normalize_soffice_path(p))
    seen: set[str] = set()
    out: list[str] = []
    for p in filtered:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _minimal_subprocess_path() -> str:
    """PATH for gunicorn/systemd (often missing ``/usr/bin``)."""
    parts = [
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    extra = (os.environ.get("PATH") or "").split(":")
    seen: set[str] = set()
    out: list[str] = []
    for p in parts + extra:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return ":".join(out) if out else "/usr/bin:/bin"


def _is_shell_script(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(128)
    except OSError:
        return False
    return head.startswith(b"#!")


def _program_soffice_in_tree(root: str) -> str | None:
    wrapper = os.path.join(root, "program", "soffice")
    if os.path.isfile(wrapper):
        return wrapper
    binary = os.path.join(root, "program", "soffice.bin")
    if os.path.isfile(binary):
        return binary
    return None


def _expand_soffice_launcher(path: str) -> list[str]:
    """
    Map a distro ``libreoffice`` shell script to the real ``program/soffice`` binary.

    Wrappers call ``dirname``, ``grep``, etc.; under systemd they fail unless PATH is set.
    """
    out: list[str] = []
    if not os.path.isfile(path):
        return out
    if not _is_shell_script(path):
        return [path]
    real = os.path.realpath(path)
    d = os.path.dirname(real)
    for root in (
        d,
        os.path.dirname(d),
        os.path.join(d, "libreoffice"),
        os.path.join(os.path.dirname(d), "libreoffice"),
    ):
        p = _program_soffice_in_tree(root)
        if p and p not in out:
            out.append(p)
    for p in _discover_linux_soffice_paths() + list(_LINUX_SOFFICE_STATIC_PATHS):
        if os.path.isfile(p) and p not in out:
            out.append(p)
    return out


def _lo_program_dir(soffice_path: str) -> str | None:
    """Directory containing ``soffice`` when installed as ``.../libreoffice/program/soffice``."""
    real = os.path.realpath(soffice_path)
    d = os.path.dirname(real)
    if os.path.basename(d) == "program":
        return d
    return None


def _soffice_subprocess_env(work_dir: str, soffice_path: str | None = None) -> dict[str, str]:
    """
    Environment for headless LibreOffice under systemd/gunicorn.

    Without a writable ``HOME``, isolated user profile, and a normal PATH, conversion
    often fails even when ``/usr/local/bin/libreoffice`` exists as a shell wrapper.

    Invoking ``program/soffice`` directly (not the distro wrapper) requires ``LD_LIBRARY_PATH``
    pointing at that ``program`` directory — otherwise ``--version`` may work but PDF conversion fails.
    """
    env = os.environ.copy()
    profile_dir = os.path.join(work_dir, "lo_profile")
    os.makedirs(profile_dir, exist_ok=True)
    env["HOME"] = work_dir
    env["TMPDIR"] = work_dir
    env["PATH"] = _minimal_subprocess_path()
    env["SAL_USE_VCLPLUGIN"] = "svp"
    env["SAL_DISABLE_OPENCL"] = "1"
    if soffice_path:
        prog = _lo_program_dir(soffice_path)
        if prog:
            old_lp = env.get("LD_LIBRARY_PATH", "").strip()
            env["LD_LIBRARY_PATH"] = f"{prog}:{old_lp}" if old_lp else prog
            env["UNO_PATH"] = prog
    return env


def _soffice_convert_filter(source_ext: str) -> str:
    ext = (source_ext or "").lstrip(".").lower()
    if ext == "docx":
        return "pdf:writer_pdf_Export"
    if ext == "odt":
        return "pdf:writer_pdf_Export"
    if ext == "doc":
        return "pdf:writer_pdf_Export"
    return "pdf"


_SOFFICE_EXIT_PROFILE_INIT = 81


def _soffice_command(soffice: str, *args: str) -> list[str]:
    """Build argv for LibreOffice; use ``program/soffice`` and ``/bin/bash`` when needed."""
    path = _normalize_soffice_path(soffice)
    if not path:
        return list(args)
    if _is_shell_script(path):
        return ["/bin/bash", path, *args]
    return [path, *args]


def _run_soffice(cmd: list[str], env: dict[str, str], cwd: str, timeout: int) -> subprocess.CompletedProcess:
    """
    Run LibreOffice, retrying exit code 81 (first-time user profile creation).

    Always uses ``program/soffice`` (via ``_soffice_command``), never ``soffice.bin`` alone.
    """
    if not cmd:
        raise ValueError("empty soffice command")
    cmd = _soffice_command(cmd[0], *cmd[1:])
    last: subprocess.CompletedProcess | None = None
    for _ in range(5):
        last = subprocess.run(
            cmd,
            capture_output=True,
            env=env,
            cwd=cwd,
            timeout=timeout,
        )
        if last.returncode == 0:
            return last
        if last.returncode != _SOFFICE_EXIT_PROFILE_INIT:
            break
    assert last is not None
    last.check_returncode()
    return last


def _verify_soffice_binary(path: str) -> bool:
    path = _normalize_soffice_path(path)
    if not os.path.isfile(path):
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="mf-lo-probe-") as tmp:
            env = _soffice_subprocess_env(tmp, path)
            _run_soffice(
                _soffice_command(path, "--headless", "--version"),
                env,
                tmp,
                timeout=30,
            )
        return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _resolve_soffice_binary() -> str | None:
    global _SOFFICE_RESOLVED
    if _SOFFICE_RESOLVED is not False:
        return _SOFFICE_RESOLVED or None
    resolved: str | None = None
    for p in _soffice_candidate_paths():
        if _verify_soffice_binary(p):
            resolved = _normalize_soffice_path(p)
            break
    _SOFFICE_RESOLVED = resolved
    return resolved


def _format_soffice_subprocess_error(
    exc: subprocess.CalledProcessError | subprocess.TimeoutExpired | subprocess.CompletedProcess,
    soffice: str,
    cmd: list[str],
) -> str:
    parts: list[str] = []
    if isinstance(exc, subprocess.CalledProcessError):
        parts.append(f"exit={exc.returncode}")
        err_b = (exc.stderr or b"") + (exc.stdout or b"")
    elif isinstance(exc, subprocess.CompletedProcess):
        err_b = (exc.stderr or b"") + (exc.stdout or b"")
    elif isinstance(exc, subprocess.TimeoutExpired):
        parts.append("timeout")
        err_b = (getattr(exc, "stderr", None) or b"") + (getattr(exc, "stdout", None) or b"")
    else:
        err_b = b""
    if err_b:
        parts.append(err_b[:1200].decode("utf-8", errors="replace").strip())
    prog = _lo_program_dir(soffice)
    if prog:
        parts.append(f"(program dir: {prog})")
    parts.append("cmd: " + " ".join(cmd))
    return " ".join(p for p in parts if p)


def docx_to_pdf_available() -> bool:
    return _resolve_soffice_binary() is not None


def _soffice_binary() -> str | None:
    resolved = _resolve_soffice_binary()
    return _normalize_soffice_path(resolved) if resolved else None


def libreoffice_diagnostic_report() -> str:
    """Human-readable report for ``manage.py check_libreoffice``."""
    lines = ["LibreOffice / soffice diagnostic", ""]
    configured = (
        str(getattr(settings, "MAGIFORM_SOFFICE", "") or "").strip()
        or os.environ.get("MAGIFORM_SOFFICE", "").strip()
    )
    lines.append(f"MAGIFORM_SOFFICE (settings/env): {configured or '(not set)'}")
    if configured:
        norm = _normalize_soffice_path(configured)
        if norm != configured:
            lines.append(f"  normalized to: {norm}")
        if os.path.isfile(configured):
            lines.append(f"  configured is shell script: {_is_shell_script(configured)}")
        if configured.endswith("soffice.bin"):
            lines.append(
                "  WARNING: MAGIFORM_SOFFICE must be program/soffice, not soffice.bin (exit 81 on convert)."
            )
    lines.append(f"PATH (process): {os.environ.get('PATH', '')}")
    lines.append(f"PATH (subprocess): {_minimal_subprocess_path()}")
    lines.append("")
    lines.append("Candidates (after expanding wrappers):")
    for p in _soffice_candidate_paths():
        exists = os.path.isfile(p)
        ok = _verify_soffice_binary(p) if exists else False
        shell = _is_shell_script(p) if exists else False
        lines.append(f"  - {p}: exists={exists} shell={shell} runs={ok}")
    lines.append("")
    resolved = _resolve_soffice_binary()
    lines.append(f"Selected binary: {resolved or '(none)'}")
    if resolved:
        with tempfile.TemporaryDirectory(prefix="mf-lo-diag-") as tmp:
            env = _soffice_subprocess_env(tmp, resolved)
            lines.append(f"  LD_LIBRARY_PATH (subprocess): {env.get('LD_LIBRARY_PATH', '(unset)')}")
    lines.append(f"docx_to_pdf_available(): {docx_to_pdf_available()}")
    if not resolved:
        lines.append("")
        lines.append(
            "No working soffice found. On Amazon Linux 2023, LibreOffice is not in "
            "/usr/lib64/libreoffice until installed — use Document Foundation RPMs under /opt "
            "(see DEPLOY.md). Quick check: find /opt -name soffice 2>/dev/null"
        )
    return "\n".join(lines)


def print_template_merge_capabilities(form: Form) -> dict[str, bool | str]:
    """
    Whether merged output can be shown or downloaded as PDF, and fallbacks when LibreOffice is missing.

    Used by the manage document viewer and the public submission track page.
    """
    has_primary = bool(form.print_template)
    odt_store = getattr(form, "print_template_odt", None)
    has_odt_secondary = bool(odt_store)
    pl = (form.print_template.name or "").lower() if has_primary else ""
    merged_pdf_available = False
    if has_primary:
        if pl.endswith(".pdf"):
            merged_pdf_available = True
        elif pl.endswith(".docx") and docx_to_pdf_available():
            merged_pdf_available = True
    elif has_odt_secondary and docx_to_pdf_available():
        merged_pdf_available = True
    show_docx_download = has_primary and pl.endswith(".docx") and not merged_pdf_available
    show_odt_download = has_odt_secondary and not merged_pdf_available
    has_merge_output = has_primary or has_odt_secondary
    return {
        "has_print_template": has_primary,
        "has_odt_secondary": has_odt_secondary,
        "primary_name_lower": pl,
        "merged_pdf_available": merged_pdf_available,
        "show_docx_download": show_docx_download,
        "show_odt_download": show_odt_download,
        "has_merge_output": has_merge_output,
    }


def libreoffice_bytes_to_pdf(source_bytes: bytes, base_name: str, source_ext: str) -> bytes:
    """
    Convert ``source_bytes`` (DOCX, ODT, or legacy DOC) to PDF using headless LibreOffice.

    ``base_name`` is a filename stem (no extension); ``source_ext`` is e.g. ``docx``, ``odt``, or ``doc``.
    """
    global _SOFFICE_RESOLVED

    soffice = _normalize_soffice_path(_soffice_binary() or "")
    if not soffice:
        raise PrintMergeError(
            "PDF export needs LibreOffice. "
            "Install ``soffice`` on the server or set MAGIFORM_SOFFICE to its full path."
        )
    ext = (source_ext or "").lstrip(".").lower()
    if ext not in ("docx", "odt", "doc"):
        raise PrintMergeError("Internal error: unsupported source type for PDF conversion.")
    safe_base = re.sub(r"[^a-zA-Z0-9_-]+", "_", base_name).strip("_") or "document"
    with tempfile.TemporaryDirectory(prefix="mf-lo-convert-") as tmp:
        src_path = os.path.join(tmp, f"{safe_base}.{ext}")
        with open(src_path, "wb") as f:
            f.write(source_bytes)
        env = _soffice_subprocess_env(tmp, soffice)
        lo_profile_uri = Path(os.path.join(tmp, "lo_profile")).resolve().as_uri()
        convert_to = _soffice_convert_filter(ext)
        profile_arg = f"-env:UserInstallation={lo_profile_uri}"
        # Warm profile in this tmp dir (avoids exit 81 on the convert invocation).
        try:
            _run_soffice(
                _soffice_command(
                    soffice,
                    "--headless",
                    "--norestore",
                    profile_arg,
                    "--version",
                ),
                env,
                tmp,
                timeout=60,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        cmd = _soffice_command(
            soffice,
            "--headless",
            "--invisible",
            "--norestore",
            "--nofirststartwizard",
            profile_arg,
            "--convert-to",
            convert_to,
            "--outdir",
            tmp,
            src_path,
        )
        try:
            completed = _run_soffice(cmd, env, tmp, timeout=180)
        except FileNotFoundError as exc:
            _SOFFICE_RESOLVED = False
            raise PrintMergeError(
                "LibreOffice binary not found. Set MAGIFORM_SOFFICE to the full path and restart the app."
            ) from exc
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            _SOFFICE_RESOLVED = False
            detail = _format_soffice_subprocess_error(exc, soffice, cmd)
            hint = ""
            if soffice.endswith("soffice.bin"):
                hint = (
                    " Use program/soffice (not soffice.bin) — e.g. "
                    f"{_normalize_soffice_path(soffice)}"
                )
            elif _is_shell_script(soffice) and not _lo_program_dir(soffice):
                hint = (
                    " Set MAGIFORM_SOFFICE to program/soffice under /opt/libreoffice* "
                    "(run: python manage.py check_libreoffice)."
                )
            elif not _lo_program_dir(soffice) and sys.platform.startswith("linux"):
                hint = (
                    " Try MAGIFORM_SOFFICE=/usr/lib64/libreoffice/program/soffice "
                    "or install libreoffice-headless."
                )
            raise PrintMergeError(
                "LibreOffice could not convert the document to PDF."
                + (f" {detail}" if detail else "")
                + hint
            ) from exc
        pdf_path = os.path.join(tmp, f"{safe_base}.pdf")
        if not os.path.isfile(pdf_path):
            pdfs = [n for n in os.listdir(tmp) if n.lower().endswith(".pdf")]
            if len(pdfs) == 1:
                pdf_path = os.path.join(tmp, pdfs[0])
        if not os.path.isfile(pdf_path):
            listing = ", ".join(sorted(os.listdir(tmp))) or "(empty)"
            out_snip = ""
            if completed.stdout or completed.stderr:
                out_snip = _format_soffice_subprocess_error(
                    subprocess.CompletedProcess(cmd, 0, completed.stdout, completed.stderr),
                    soffice,
                    cmd,
                )
            raise PrintMergeError(
                "LibreOffice did not produce a PDF file. "
                f"tmpdir contents: {listing}."
                + (f" {out_snip}" if out_snip else "")
                + " Run ``python manage.py check_libreoffice`` on the server."
            )
        with open(pdf_path, "rb") as f:
            return f.read()


def merge_docx_to_pdf(docx_bytes: bytes) -> bytes:
    return libreoffice_bytes_to_pdf(docx_bytes, "merge", "docx")


def merged_document_http_response(
    data: bytes,
    filename: str,
    content_type: str,
    *,
    inline: bool,
):
    """``FileResponse`` for merged templates; PDF inline embed uses explicit disposition."""
    from django.http import FileResponse

    as_attachment = not (inline and content_type == "application/pdf")
    resp = FileResponse(
        BytesIO(data),
        as_attachment=as_attachment,
        filename=filename,
        content_type=content_type,
    )
    if inline and content_type == "application/pdf":
        safe_name = filename.replace('"', "")
        resp["Content-Disposition"] = f'inline; filename="{safe_name}"'
    return resp


def _resolve_pdf_field_value_from_context(fq_key: str, ctx: dict[str, str]) -> str | None:
    """Resolve the string to fill for a PDF AcroForm field (qualified name)."""
    if fq_key in ctx:
        return ctx[fq_key]
    tail = _pdf_logical_tail(fq_key)
    tail_nf = tail.casefold()
    tail_jinja = _jinja_safe_key(tail)
    for key in (tail, tail_jinja):
        if key in ctx:
            return ctx[key]
    for k, v in ctx.items():
        k_s = str(k)
        if k_s.casefold() == tail_nf or _jinja_safe_key(k_s) == tail_jinja:
            return v
    for k, v in ctx.items():
        k_s = str(k)
        if fq_key.endswith("." + k_s) or fq_key.endswith("." + _jinja_safe_key(k_s)):
            return v
    return None


def _pdf_logical_tail(fq_pdf_name: str) -> str:
    """
    Acrobat / LiveCycle exports often encode indices as segments like ``name[0]``.
    Normalize to compare against MagicForms slug names.

    PDF ``/T`` entries stored as names often appear as the last segment with a leading slash
    (e.g. ``/fullname``). Strip that slash so we match MagicForms field ``fullname``.
    """
    deindexed = re.sub(r"\[\d+\]", "", fq_pdf_name)
    segments = [p for p in deindexed.replace("..", ".").split(".") if p]
    tail = segments[-1] if segments else deindexed
    return tail.lstrip("/")


def expand_pdf_form_field_context(reader: Any, flat_ctx: dict[str, str]) -> dict[str, str]:
    """
    Duplicate context keys under PDF **fully-qualified** AcroForm names so PyPDF matching succeeds.

    ``update_page_form_field_values`` requires keys that equal either the logical ``/T`` on the field or
    the writer's `_get_qualified_field_name()` (often ``parent.child`` / ``something[0].leaf`` strings).
    We only expose short slug keys from ``build_print_context`` unless the PDF uses top-level-only names.

    Fields may use **alternate mapping** ``/TM``: `_get_qualified_field_name` returns ``/TM`` when
    present on that dictionary, so we register the same value under the TM string as a dict key.
    """
    pdf_fields = reader.get_fields()
    if not pdf_fields:
        return flat_ctx

    out = dict(flat_ctx)

    for pdf_fq, field_obj in pdf_fields.items():
        fq_key = str(pdf_fq)
        if fq_key in out:
            continue

        value = _resolve_pdf_field_value_from_context(fq_key, flat_ctx)

        mapped_key: str | None = None
        tm_raw = None
        if hasattr(field_obj, "get"):
            tm_raw = field_obj.get("/TM")
            if tm_raw is not None:
                mapped_key = str(tm_raw)
        if value is None and mapped_key and mapped_key in flat_ctx:
            value = flat_ctx[mapped_key]

        if value is not None:
            out[fq_key] = value
            if mapped_key:
                out[mapped_key] = value
            if tm_raw is not None:
                out[tm_raw] = value

    return out


def _iter_pdf_widget_parent_annotations(writer: Any):
    """Yield (annotation_dict, parent_field_dict) for each Widget, mirroring PyPDF's fill loop."""
    from pypdf.constants import PageAttributes as PG
    from pypdf.generic import DictionaryObject

    for page in writer.pages:
        annots = page.get(PG.ANNOTS)
        if not annots:
            continue
        for aref in annots:
            try:
                annot = aref.get_object()
            except Exception:
                continue
            if annot.get("/Subtype") != "/Widget":
                continue
            if "/FT" in annot and "/T" in annot:
                parent_annotation = annot
            else:
                parent_obj = annot.get("/Parent")
                if parent_obj is None:
                    continue
                parent_annotation = parent_obj.get_object()
                if not isinstance(parent_annotation, DictionaryObject):
                    continue
            yield annot, parent_annotation


def _propagate_inherited_ft(writer: Any) -> None:
    """
    PyPDF only rebuilds text appearances when ``/FT`` is present on the **same** dictionary it uses
    for ``/V``. Many PDFs inherit ``/FT`` from an ancestor field; copy it down so values stay visible.
    """
    from pypdf.constants import FieldDictionaryAttributes as FA
    from pypdf.generic import NameObject

    for _annot, parent_annotation in _iter_pdf_widget_parent_annotations(writer):
        if parent_annotation.get(FA.FT):
            continue
        ancestor_ref = parent_annotation.get(FA.Parent)
        inherited = None
        while ancestor_ref is not None:
            ancestor = ancestor_ref.get_object()
            if ancestor.get(FA.FT):
                inherited = ancestor[FA.FT]
                break
            ancestor_ref = ancestor.get(FA.Parent)
        if inherited is not None:
            parent_annotation[NameObject(FA.FT)] = inherited


def _enrich_pdf_context_from_page_widgets(writer: Any, flat_ctx: dict[str, str]) -> dict[str, str]:
    """
    ``reader.get_fields()`` can miss fields (or return nothing) while Widget annotations still exist.
    Walk pages and register every qualified name, ``/T``, and ``/TM`` key PyPDF may compare against.
    """
    out = dict(flat_ctx)
    for _annot, parent_annotation in _iter_pdf_widget_parent_annotations(writer):
        qname = writer._get_qualified_field_name(parent_annotation)
        value = _resolve_pdf_field_value_from_context(qname, flat_ctx)
        if value is None:
            t_raw = parent_annotation.get("/T")
            if t_raw is not None:
                ts = str(t_raw).lstrip("/")
                value = _resolve_pdf_field_value_from_context(ts, flat_ctx)
        if value is None:
            tm_raw = parent_annotation.get("/TM")
            if tm_raw is not None:
                tm_s = str(tm_raw)
                value = flat_ctx.get(tm_s) or _resolve_pdf_field_value_from_context(tm_s, flat_ctx)
        if value is None:
            continue
        if qname:
            out[qname] = value
        t_raw = parent_annotation.get("/T")
        if t_raw is not None:
            out[str(t_raw)] = value
            out[t_raw] = value
        tm_raw = parent_annotation.get("/TM")
        if tm_raw is not None:
            out[str(tm_raw)] = value
            out[tm_raw] = value
    return out


def _add_pdf_widget_native_t_aliases(writer: Any, merged: dict[str, str]) -> dict[str, str]:
    """Like `_add_pdf_native_t_aliases` but driven by page widgets when field tree metadata differs."""
    out = dict(merged)
    for _annot, parent_annotation in _iter_pdf_widget_parent_annotations(writer):
        t_raw = parent_annotation.get("/T")
        if t_raw is None:
            continue
        fq_s = writer._get_qualified_field_name(parent_annotation)
        val = merged.get(fq_s) or _resolve_pdf_field_value_from_context(fq_s, merged)
        if val is None:
            continue
        out[t_raw] = val
    return out


def _resolve_value_for_pdf_widget(parent_annotation: Any, writer: Any, flat_ctx: dict[str, str]) -> str | None:
    """
    Resolve the fill value for one AcroForm field using the same identifiers PyPDF compares
    (qualified name, ``/T``, ``/TM``), without relying on dict key equality during iteration.
    """
    qname = writer._get_qualified_field_name(parent_annotation)
    v = _resolve_pdf_field_value_from_context(qname, flat_ctx)
    if v is not None:
        return v

    t_raw = parent_annotation.get("/T")
    if t_raw is not None:
        for candidate in (str(t_raw), str(t_raw).lstrip("/")):
            if candidate in flat_ctx:
                return flat_ctx[candidate]
            got = _resolve_pdf_field_value_from_context(candidate, flat_ctx)
            if got is not None:
                return got

    tm_raw = parent_annotation.get("/TM")
    if tm_raw is not None:
        tm_s = str(tm_raw)
        if tm_s in flat_ctx:
            return flat_ctx[tm_s]
        got = _resolve_pdf_field_value_from_context(tm_s, flat_ctx)
        if got is not None:
            return got

    return None


def _effective_field_ft(field_dict: Any) -> Any:
    """Return ``/FT`` from this dictionary or the closest ancestor field (PDF inheritance)."""
    from pypdf.constants import FieldDictionaryAttributes as FA

    cur: Any = field_dict
    for _ in range(64):
        if cur is None:
            break
        ft = cur.get(FA.FT)
        if ft:
            return ft
        pref = cur.get(FA.Parent)
        if pref is None:
            break
        cur = pref.get_object()
    return None


def _direct_fill_pdf_widgets(writer: Any, flat_ctx: dict[str, str]) -> None:
    """
    Second pass: set ``/V`` and rebuild **/AP** for text/choice widgets by resolving names against
    ``flat_ctx``. PyPDF's ``update_page_form_field_values`` only applies a row when a **dict key**
    matches exactly; this pass matches the way Acrobat names fields so templates still fill when that
    lookup misses (names, ``/TM``, hierarchical tails, etc.).
    """
    from pypdf.constants import AnnotationDictionaryAttributes as AA
    from pypdf.constants import CatalogDictionary
    from pypdf.constants import FieldDictionaryAttributes as FA
    from pypdf.generic import DictionaryObject, IndirectObject, NameObject, TextStringObject
    from pypdf.generic._appearance_stream import TextStreamAppearance

    acro_ref = writer._root_object.get(CatalogDictionary.ACRO_FORM)
    if acro_ref is None:
        return
    acro_form = cast(DictionaryObject, acro_ref.get_object())

    for annotation, parent_annotation in _iter_pdf_widget_parent_annotations(writer):
        val = _resolve_value_for_pdf_widget(parent_annotation, writer, flat_ctx)
        if val is None:
            continue
        if AA.Rect not in annotation:
            continue

        eft = _effective_field_ft(parent_annotation)
        if eft is None or eft == "/Btn":
            continue

        if eft == "/Ch" and "/I" in parent_annotation:
            del parent_annotation["/I"]

        parent_annotation[NameObject(FA.V)] = TextStringObject(val)

        if eft not in ("/Tx", "/Ch"):
            continue

        try:
            appearance_stream_obj = TextStreamAppearance.from_text_annotation(
                acro_form, parent_annotation, annotation
            )
        except Exception:
            continue

        if AA.AP not in annotation:
            annotation[NameObject(AA.AP)] = DictionaryObject(
                {NameObject("/N"): writer._add_object(appearance_stream_obj)}
            )
        elif "/N" not in (ap := cast(DictionaryObject, annotation[AA.AP])):
            ap[NameObject("/N")] = writer._add_object(appearance_stream_obj)
        else:
            try:
                n_ref = annotation[AA.AP]["/N"]
                n = n_ref.indirect_reference.idnum  # type: ignore[union-attr]
                writer._objects[n - 1] = appearance_stream_obj
                appearance_stream_obj.indirect_reference = IndirectObject(n, 0, writer)
            except Exception:
                ap = cast(DictionaryObject, annotation[AA.AP])
                ap[NameObject("/N")] = writer._add_object(appearance_stream_obj)


def _add_pdf_native_t_aliases(reader: Any, merged: dict[str, str]) -> dict[str, str]:
    """
    PyPDF matches ``fields`` keys with ``parent_annotation.get('/T')`` using ``==``.

    Many PDFs store ``/T`` as ``NameObject('/fullname')`` (with a leading slash). That is **not**
    equal to the Python string ``'fullname'``, so values never apply unless we also register the
    native PDF object (or an equal ``NameObject``) as a dict key.
    """
    pdf_fields = reader.get_fields()
    if not pdf_fields:
        return merged

    out = dict(merged)
    for _fq, field_obj in pdf_fields.items():
        if not hasattr(field_obj, "get"):
            continue
        t_raw = field_obj.get("/T")
        if t_raw is None:
            continue
        fq_s = str(_fq)
        val = out.get(fq_s) or _resolve_pdf_field_value_from_context(fq_s, out)
        if val is None:
            continue
        out[t_raw] = val
    return out


def fill_pdf_acroform(template_bytes: bytes, context: dict[str, Any]) -> bytes:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise PrintMergeError("pypdf is not installed.") from exc

    reader = PdfReader(BytesIO(template_bytes))
    writer = PdfWriter()
    writer.append(reader)
    _propagate_inherited_ft(writer)
    str_ctx = {k: str(v) for k, v in context.items()}
    str_ctx = expand_pdf_form_field_context(reader, str_ctx)
    str_ctx = _enrich_pdf_context_from_page_widgets(writer, str_ctx)
    str_ctx = _add_pdf_native_t_aliases(reader, str_ctx)
    str_ctx = _add_pdf_widget_native_t_aliases(writer, str_ctx)
    if not writer.pages:
        raise PrintMergeError("The PDF template has no pages.")
    try:
        writer.update_page_form_field_values(writer.pages, str_ctx, auto_regenerate=True)
    except Exception as exc:
        raise PrintMergeError(
            "Could not fill PDF form fields. Ensure AcroForm field names match your form field internal names."
        ) from exc
    _direct_fill_pdf_widgets(writer, str_ctx)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def _stamp_signatures(pdf_bytes: bytes, submission: FormSubmission) -> bytes:
    """Apply hand-drawn signature placements (document page right-click → sign)."""
    from .pdf_signatures import stamp_signature_placements

    placements = list(submission.signature_placements.all())
    if not placements:
        return pdf_bytes
    return stamp_signature_placements(pdf_bytes, placements)


def render_submission_document(
    submission: FormSubmission,
    output: str,
) -> tuple[bytes, str, str]:
    """
    ``output`` is ``docx``, ``pdf``, or ``odt``.

    Primary ``Form.print_template`` is DOCX or PDF (merged filled document).
    Optional ``Form.print_template_odt`` holds ODT for staff download; answers are not merged into ODT.

    Returns ``(bytes, filename, content_type)``.
    """
    form = submission.form
    primary = form.print_template
    odt_store = getattr(form, "print_template_odt", None)

    if not primary and not odt_store:
        raise PrintMergeError("This form has no print template uploaded.")
    for store in (primary, odt_store):
        if store and not store.storage.exists(store.name):
            raise PrintMergeError(
                _("The print template file is missing from the server's media storage: %(name)s.")
                % {"name": store.name}
            )

    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", form.slug)[:80] or "form"
    ref = str(submission.reference_token)[:12]
    pn = (primary.name or "").lower() if primary else ""

    if output == "docx":
        if not primary or not pn.endswith(".docx"):
            raise PrintMergeError(
                _("Merged DOCX requires a .docx file in the primary print template field.")
            )
        tmpl_bytes = primary.read()
        data = merge_docx(tmpl_bytes, submission)
        return (
            data,
            f"{slug}-{ref}.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    if output == "odt":
        if odt_store:
            tmpl_bytes = odt_store.read()
            return (
                tmpl_bytes,
                f"{slug}-{ref}.odt",
                "application/vnd.oasis.opendocument.text",
            )
        raise PrintMergeError(
            _("Upload an ODT file in the optional ODT print template field to enable ODT download.")
        )

    if output == "pdf":
        entity = form.entity
        if primary and pn.endswith(".pdf"):
            tmpl_bytes = primary.read()
            ctx = build_print_context(submission)
            data = fill_pdf_acroform(tmpl_bytes, ctx)
            data = stamp_entity_logo_on_pdf(data, entity)
            data = _stamp_signatures(data, submission)
            return data, f"{slug}-{ref}.pdf", "application/pdf"
        if primary and pn.endswith(".docx"):
            tmpl_bytes = primary.read()
            docx_out = merge_docx(tmpl_bytes, submission)
            pdf_out = merge_docx_to_pdf(docx_out)
            pdf_out = stamp_entity_logo_on_pdf(pdf_out, entity)
            pdf_out = _stamp_signatures(pdf_out, submission)
            return pdf_out, f"{slug}-{ref}.pdf", "application/pdf"
        if odt_store:
            tmpl_bytes = odt_store.read()
            pdf_out = libreoffice_bytes_to_pdf(tmpl_bytes, f"{slug}_{ref}", "odt")
            pdf_out = stamp_entity_logo_on_pdf(pdf_out, entity)
            pdf_out = _stamp_signatures(pdf_out, submission)
            return pdf_out, f"{slug}-{ref}.pdf", "application/pdf"
        raise PrintMergeError(
            _(
                "PDF needs a DOCX or PDF in the primary template field, or an ODT in the optional ODT field."
            )
        )

    raise PrintMergeError(_("Unsupported output format."))
