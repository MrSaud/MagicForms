"""Public views for outbound integration (signed file download)."""

from __future__ import annotations

import mimetypes

from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET

from magicforms.models import SubmissionValue

from .file_urls import file_download_token_valid


@require_GET
def outbound_file_download(request):
    """
    Download a respondent file upload when ``token`` is a valid signed
    ``SubmissionValue`` id (short-lived; for external systems via outbound POST).
    """
    sv_id = file_download_token_valid(request.GET.get("token", ""))
    if sv_id is None:
        raise Http404()
    sv = (
        SubmissionValue.objects.select_related("field", "submission")
        .filter(pk=sv_id)
        .first()
    )
    if sv is None or not sv.attachment:
        raise Http404()
    name = (sv.value or "").strip() or sv.attachment.name.split("/")[-1]
    content_type, _encoding = mimetypes.guess_type(name)
    try:
        fh = sv.attachment.open("rb")
    except OSError:
        raise Http404() from None
    return FileResponse(
        fh,
        as_attachment=True,
        filename=name,
        content_type=content_type or "application/octet-stream",
    )
