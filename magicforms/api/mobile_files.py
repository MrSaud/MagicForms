"""Mobile API: download submission field file attachments."""

from __future__ import annotations

import os

from django.http import FileResponse, Http404, HttpRequest
from django.shortcuts import get_object_or_404

from magicforms.api.mobile_content import _get_submission_for_mobile
from magicforms.models import FieldType, SubmissionValue


def submission_value_attachment(request: HttpRequest, submission_id: int, value_id: int):
    submission = _get_submission_for_mobile(request, submission_id)
    sv = get_object_or_404(
        SubmissionValue.objects.select_related("field"),
        pk=value_id,
        submission=submission,
    )
    if sv.field.field_type != FieldType.FILE or not sv.attachment:
        raise Http404
    name = (sv.value or "").strip() or os.path.basename(sv.attachment.name)
    try:
        fh = sv.attachment.open("rb")
    except OSError:
        raise Http404
    return FileResponse(fh, as_attachment=False, filename=name)
