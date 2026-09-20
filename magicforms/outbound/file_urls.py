"""Signed download URLs for submission file fields in outbound POST payloads."""

from __future__ import annotations

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.urls import reverse

_SIGNER_SALT = "magicforms.outbound.submission-file.v1"


def outbound_file_url_max_age() -> int:
    return int(getattr(settings, "OUTBOUND_FILE_URL_MAX_AGE", 3600))


def sign_submission_value_download(submission_value_id: int) -> str:
    signer = TimestampSigner(salt=_SIGNER_SALT)
    return signer.sign(str(int(submission_value_id)))


def unsign_submission_value_download(token: str) -> int:
    signer = TimestampSigner(salt=_SIGNER_SALT)
    return int(signer.unsign(token, max_age=outbound_file_url_max_age()))


def outbound_file_download_path(token: str) -> str:
    from urllib.parse import urlencode

    return reverse("magicforms:outbound_file_download") + "?" + urlencode({"token": token})


def absolute_outbound_file_url(submission_value_id: int, request=None) -> str:
    token = sign_submission_value_download(submission_value_id)
    path = outbound_file_download_path(token)
    if request is not None:
        return request.build_absolute_uri(path)
    base = (getattr(settings, "MAGIFORM_OUTBOUND_FILE_BASE_URL", "") or "").strip().rstrip("/")
    if not base:
        from magicforms.subdomain import apex_site_url

        base = apex_site_url(request).rstrip("/")
    return f"{base}{path}"


def file_download_token_valid(token: str) -> int | None:
    if not (token or "").strip():
        return None
    try:
        return unsign_submission_value_download(token.strip())
    except (BadSignature, SignatureExpired, ValueError):
        return None
