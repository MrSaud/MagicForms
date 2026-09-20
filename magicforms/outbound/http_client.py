"""Send outbound POST requests with auth headers and redaction for logs."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

from magicforms.models import FormOutboundConfig
from magicforms.outbound.crypto import decrypt_secret

_DEFAULT_USER_AGENT = "MagicForms-Outbound/1.0"
_AUTH_NONE = FormOutboundConfig.AuthType.NONE


def _auth_headers(config, body_bytes: bytes) -> dict[str, str]:
    secret = decrypt_secret(getattr(config, "secret_encrypted", "") or "")
    headers: dict[str, str] = {}
    if not secret:
        return headers
    auth_type = getattr(config, "auth_type", _AUTH_NONE)
    header_name = (getattr(config, "auth_header_name", None) or "").strip() or "Authorization"
    if auth_type == FormOutboundConfig.AuthType.BEARER:
        if header_name.lower() == "authorization":
            headers["Authorization"] = f"Bearer {secret}"
        else:
            headers[header_name] = secret
    elif auth_type == FormOutboundConfig.AuthType.HEADER:
        headers[header_name] = secret
    elif auth_type == FormOutboundConfig.AuthType.BASIC:
        import base64

        token = base64.b64encode(secret.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    elif auth_type == FormOutboundConfig.AuthType.HMAC_SHA256:
        ts = str(int(time.time()))
        sig_header = (getattr(config, "hmac_header_name", None) or "").strip() or "X-Signature"
        signed = hmac.new(secret.encode("utf-8"), body_bytes + ts.encode("utf-8"), hashlib.sha256).hexdigest()
        headers[sig_header] = signed
        headers["X-Timestamp"] = ts
    return headers


def _merge_custom_headers(config) -> dict[str, str]:
    raw = getattr(config, "custom_headers_json", None) or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if not key:
            continue
        out[key] = str(v)
    return out


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    sensitive = {"authorization", "x-api-key", "api-key", "x-signature"}
    out = {}
    for k, v in headers.items():
        if k.lower() in sensitive or "token" in k.lower() or "secret" in k.lower():
            out[k] = "***"
        else:
            out[k] = v
    return out


def send_json_integration_post(
    config,
    *,
    url: str,
    payload: dict[str, Any],
    extra_headers: dict[str, str] | None = None,
    idempotency_key: str = "",
) -> tuple[int, str, dict[str, str], dict[str, str]]:
    """
    POST JSON with integration auth. Returns (status_code, body_truncated, redacted_headers, sent_headers).
    """
    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    user_agent = getattr(settings, "OUTBOUND_USER_AGENT", None) or _DEFAULT_USER_AGENT
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "User-Agent": user_agent,
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    if extra_headers:
        headers.update(extra_headers)
    headers.update(_merge_custom_headers(config))
    headers.update(_auth_headers(config, body_bytes))
    timeout = max(5, min(int(getattr(config, "timeout_seconds", None) or 20), 60))
    req = urllib.request.Request(url, data=body_bytes, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(8192).decode("utf-8", errors="replace")
            return resp.status, raw[:4000], redact_headers(headers), headers
    except urllib.error.HTTPError as exc:
        raw = exc.read(8192).decode("utf-8", errors="replace")
        return exc.code, raw[:4000], redact_headers(headers), headers
    except urllib.error.URLError as exc:
        raise ConnectionError(str(exc.reason)) from exc


def send_outbound_post(
    config: FormOutboundConfig,
    *,
    url: str,
    payload: dict[str, Any],
    idempotency_key: str,
    trigger: str,
    submission_ref: str,
    form_id: int,
    test_mode: bool = False,
) -> tuple[int, str, dict[str, str], dict[str, str]]:
    """POST JSON payload for outbound delivery."""
    extra = {
        "X-MagicForms-Event-Id": idempotency_key,
        "X-MagicForms-Trigger": trigger,
        "X-MagicForms-Form-Id": str(form_id),
        "X-MagicForms-Submission-Ref": submission_ref,
    }
    if test_mode:
        extra["X-MagicForms-Test"] = "1"
    return send_json_integration_post(
        config,
        url=url,
        payload=payload,
        extra_headers=extra,
        idempotency_key=idempotency_key,
    )
