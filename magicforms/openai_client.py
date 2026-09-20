"""Shared OpenAI-compatible Chat Completions helpers (urllib, no SDK)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings


def openai_api_key() -> str:
    return (getattr(settings, "OPENAI_API_KEY", "") or "").strip()


def openai_api_base() -> str:
    return (getattr(settings, "OPENAI_API_BASE", "https://api.openai.com/v1") or "https://api.openai.com/v1").rstrip(
        "/"
    )


def parse_openai_error_body(raw: str) -> str:
    """Extract a human-readable message from an OpenAI error JSON body."""
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text[:500]
    err = data.get("error")
    if isinstance(err, dict):
        msg = (err.get("message") or "").strip()
        code = (err.get("code") or err.get("type") or "").strip()
        if msg and code:
            return f"{msg} ({code})"
        return msg or text[:500]
    if isinstance(err, str):
        return err[:500]
    return text[:500]


def format_openai_exception(exc: BaseException, *, http_body: str = "") -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = http_body or exc.read().decode("utf-8")
        except Exception:
            body = ""
        parsed = parse_openai_error_body(body)
        if parsed:
            return f"OpenAI HTTP {exc.code}: {parsed}"
        return f"OpenAI HTTP {exc.code}: {exc.reason}"
    return str(exc)


def chat_completions_json(
    *,
    system: str,
    user_msg: str,
    model: str,
    warnings: list[str],
    timeout: int = 45,
    max_user_chars: int = 4000,
    temperature: float = 0.15,
) -> dict | None:
    """POST ``/chat/completions`` with JSON response format; return parsed object or None."""
    key = openai_api_key()
    if not key:
        return None
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": (user_msg or "")[:max_user_chars]},
        ],
        "temperature": temperature,
    }
    req = urllib.request.Request(
        f"{openai_api_base()}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
        except Exception:
            raw = ""
        warnings.append(format_openai_exception(e, http_body=raw))
    except Exception as exc:
        warnings.append(format_openai_exception(exc))
    return None


def first_warning_message(warnings: list[str]) -> str:
    if not warnings:
        return ""
    return (warnings[0] or "").strip()
