"""Mobile API: merged print templates and submission document attachments."""

from __future__ import annotations

import os
from io import BytesIO

from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _

from magicforms.api.mobile_content import _get_submission_for_mobile
from magicforms.attachment_utils import attachment_source_ext_for_pdf
from magicforms.models import SubmissionAttachment
from magicforms.print_merge import (
    PrintMergeError,
    docx_to_pdf_available,
    print_template_merge_capabilities,
    render_submission_document,
)
from magicforms.pdf_branding import stamp_entity_logo_on_pdf


def _mobile_api_path(submission_id: int, suffix: str) -> str:
    return f"/api/v1/inbox/{submission_id}/documents{suffix}"


def documents_block_payload(request: HttpRequest, submission) -> dict:
    form = submission.form
    caps = print_template_merge_capabilities(form)
    pl = str(caps.get("primary_name_lower") or "")

    merged = None
    if caps.get("has_merge_output"):
        merged = {
            "has_merge_output": True,
            "can_view_pdf_inline": bool(caps.get("merged_pdf_available")),
            "show_docx_download": bool(caps.get("has_print_template")) and pl.endswith(".docx"),
            "show_odt_download": bool(caps.get("has_odt_secondary")),
            "show_pdf_download": bool(caps.get("merged_pdf_available")),
            "pdf_api_path": _mobile_api_path(submission.pk, "/merged/pdf/"),
            "docx_api_path": _mobile_api_path(submission.pk, "/merged/docx/"),
            "odt_api_path": _mobile_api_path(submission.pk, "/merged/odt/"),
        }

    attachments = []
    lo = docx_to_pdf_available()
    for doc in submission.document_attachments.all():
        filename = os.path.basename(doc.file.name or "") or f"document-{doc.pk}"
        lower = filename.lower()
        is_pdf = lower.endswith(".pdf")
        ext = attachment_source_ext_for_pdf(doc)
        can_preview = is_pdf or (ext is not None and lo)
        attachments.append(
            {
                "id": doc.pk,
                "title": (doc.title or "").strip(),
                "filename": filename,
                "is_pdf": is_pdf,
                "can_preview_pdf": can_preview,
                "download_api_path": _mobile_api_path(
                    submission.pk, f"/attachments/{doc.pk}/"
                ),
                "pdf_api_path": (
                    _mobile_api_path(submission.pk, f"/attachments/{doc.pk}/pdf/")
                    if can_preview and not is_pdf
                    else ""
                ),
            }
        )

    return {"merged": merged, "attachments": attachments}


def submission_merged_document_mobile(
    request: HttpRequest, submission_id: int, fmt: str
):
    fmt = (fmt or "").lower()
    if fmt not in ("docx", "pdf", "odt"):
        raise Http404
    inline = request.GET.get("inline") in ("1", "true", "yes")
    submission = _get_submission_for_mobile(request, submission_id)
    try:
        data, filename, content_type = render_submission_document(submission, fmt)
    except PrintMergeError as exc:
        return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
    return FileResponse(
        BytesIO(data),
        as_attachment=not inline and fmt != "pdf",
        filename=filename,
        content_type=content_type,
    )


def submission_attachment_download_mobile(
    request: HttpRequest, submission_id: int, attachment_id: int
):
    submission = _get_submission_for_mobile(request, submission_id)
    att = get_object_or_404(
        SubmissionAttachment, pk=attachment_id, submission=submission
    )
    if not att.file:
        raise Http404
    name = os.path.basename(att.file.name) or f"attachment-{att.pk}"
    try:
        fh = att.file.open("rb")
    except OSError:
        raise Http404
    return FileResponse(fh, as_attachment=False, filename=name)


def submission_attachment_pdf_mobile(
    request: HttpRequest, submission_id: int, attachment_id: int
):
    from magicforms.print_merge import libreoffice_bytes_to_pdf

    inline = request.GET.get("inline") in ("1", "true", "yes")
    submission = _get_submission_for_mobile(request, submission_id)
    att = get_object_or_404(
        SubmissionAttachment, pk=attachment_id, submission=submission
    )
    filename = os.path.basename(att.file.name or "")
    if filename.lower().endswith(".pdf"):
        try:
            fh = att.file.open("rb")
        except OSError:
            raise Http404
        return FileResponse(fh, as_attachment=not inline, filename=filename)

    ext = attachment_source_ext_for_pdf(att)
    if not ext or not docx_to_pdf_available():
        return HttpResponse(
            _("PDF preview is not available for this file."),
            status=400,
            content_type="text/plain; charset=utf-8",
        )
    try:
        att.file.open("rb")
        try:
            raw = att.file.read()
        finally:
            att.file.close()
        pdf_bytes = libreoffice_bytes_to_pdf(raw, f"attachment_{att.pk}", ext)
        pdf_bytes = stamp_entity_logo_on_pdf(pdf_bytes, submission.form.entity)
    except PrintMergeError as exc:
        return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
    stem = os.path.splitext(filename)[0] or f"attachment_{att.pk}"
    return FileResponse(
        BytesIO(pdf_bytes),
        as_attachment=not inline,
        filename=f"{stem}.pdf",
        content_type="application/pdf",
    )
