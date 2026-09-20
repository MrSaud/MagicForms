"""
Text-to-form engine: turn a natural-language description into a structured form spec,
then persist it as Form + FormField rows (+ default workflow step).

Public API
----------
``parse_text_to_form_spec(description)`` — returns ``(spec, warnings, backend_label)``.
``persist_parsed_form_spec(spec, user, entity)`` — saves to the database and returns ``Form``.

Optional LLM (OpenAI-compatible Chat Completions)
--------------------------------------------------
Configure in ``config/settings.py`` (from environment): ``OPENAI_API_KEY``,
``MAGIFORM_TEXT_TO_FORM_MODEL`` (default ``gpt-4o-mini``), ``MAGIFORM_INBOX_AI_MODEL``,
``OPENAI_API_BASE`` (default ``https://api.openai.com/v1``).

Without an API key, a deterministic heuristic parser is used (bullets / numbered lines,
optional ``(type)`` hints, or a JSON block).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify

from .models import Entity, FieldType, Form, FormField, OptionsLayout, WorkflowStep
from .slug_utils import unique_form_slug as _unique_form_slug


class FormEngineError(ValueError):
    """Raised when the description cannot be turned into a valid form spec."""


@dataclass
class FormFieldSpec:
    name: str
    label: str
    field_type: str
    required: bool = False
    help_text: str = ""
    choices_text: str = ""
    placeholder: str = ""


@dataclass
class ParsedFormSpec:
    title: str
    description: str = ""
    slug: str = ""
    fields: list[FormFieldSpec] = field(default_factory=list)


_ALLOWED_TYPES = {c.value for c in FieldType}

_TYPE_SYNONYMS: dict[str, str] = {
    "short text": FieldType.TEXT,
    "string": FieldType.TEXT,
    "text": FieldType.TEXT,
    "paragraph": FieldType.TEXTAREA,
    "long text": FieldType.TEXTAREA,
    "textarea": FieldType.TEXTAREA,
    "email": FieldType.EMAIL,
    "e-mail": FieldType.EMAIL,
    "number": FieldType.NUMBER,
    "numeric": FieldType.NUMBER,
    "integer": FieldType.NUMBER,
    "decimal": FieldType.NUMBER,
    "date": FieldType.DATE,
    "dropdown": FieldType.SELECT,
    "select": FieldType.SELECT,
    "choice": FieldType.SELECT,
    "radio": FieldType.RADIO,
    "checkbox": FieldType.CHECKBOX,
    "bool": FieldType.CHECKBOX,
    "boolean": FieldType.CHECKBOX,
    "checklist": FieldType.CHECKLIST,
    "multi select": FieldType.CHECKLIST,
    "multi-select": FieldType.CHECKLIST,
    "multiselect": FieldType.CHECKLIST,
    "file": FieldType.FILE,
    "upload": FieldType.FILE,
    "attachment": FieldType.FILE,
    "label": FieldType.LABEL,
    "heading": FieldType.LABEL,
    "display text": FieldType.LABEL,
    "text only": FieldType.LABEL,
    "break": FieldType.BREAK,
    "line break": FieldType.BREAK,
    "linebreak": FieldType.BREAK,
    "spacer": FieldType.BREAK,
    "newline": FieldType.BREAK,
    "hint": FieldType.HINT,
    "information": FieldType.HINT,
}


def _normalize_field_type(raw: str | None) -> str:
    if not raw:
        return FieldType.TEXT
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if key in _ALLOWED_TYPES:
        return key
    return _TYPE_SYNONYMS.get(key.replace("_", " "), FieldType.TEXT)


def _unique_field_names(labels: list[str]) -> list[str]:
    """Unique internal names for a batch of labels (AI form generation)."""
    used: set[str] = set()
    out: list[str] = []
    for label in labels:
        base = slugify(label)[:80].strip("-") or "field"
        name = base
        k = 2
        while name in used:
            suffix = f"-{k}"
            name = f"{base[: 80 - len(suffix)]}{suffix}"
            k += 1
        used.add(name)
        out.append(name)
    return out


def _try_extract_json_dict(text: str) -> dict[str, Any] | None:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
    blob = m.group(1) if m else text
    blob = blob.strip()
    if not blob.startswith("{"):
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _hint_to_type_and_choices(hint: str) -> tuple[str, str]:
    hint_clean = hint.strip()
    hint_low = hint_clean.lower()
    if "required" in hint_low:
        hint_low = re.sub(r"\brequired\b", "", hint_low, flags=re.I)
        hint_low = re.sub(r"[,;]+\s*$", "", hint_low).strip()
    choices_text = ""
    left_part = hint_low
    for sep in (":", "—", "–", "="):
        if sep in hint_clean:
            left, right = hint_clean.split(sep, 1)
            left_part = left.lower().strip()
            raw_opts = right.strip()
            if raw_opts:
                parts = re.split(r"[,|]\s*", raw_opts)
                choices_text = "\n".join(p.strip() for p in parts if p.strip())
            break

    token = (left_part.split()[0] if left_part else "") or left_part
    token = token.replace(" ", "_").replace("-", "_")
    if token in _ALLOWED_TYPES:
        ft = token
    else:
        phrase = left_part.replace("_", " ").strip()
        ft = _TYPE_SYNONYMS.get(phrase, FieldType.TEXT)
        if phrase and ft == FieldType.TEXT and phrase not in ("text", "short", ""):
            for word in phrase.split():
                if word in _TYPE_SYNONYMS:
                    ft = _TYPE_SYNONYMS[word]
                    break

    if ft in (FieldType.SELECT, FieldType.RADIO, FieldType.CHECKLIST) and not choices_text.strip():
        choices_text = "Option A\nOption B\nOption C"

    return ft, choices_text


def _parse_field_line(line: str) -> FormFieldSpec | None:
    m = re.match(r"^\s*([-*•]|\d+[\.)])\s+(.+)$", line)
    if not m:
        return None
    rest = m.group(2).strip()
    if not rest:
        return None

    required = False
    if rest.endswith("*"):
        required = True
        rest = rest[:-1].strip()

    label = rest
    help_text = ""
    choices_text = ""
    ft = FieldType.TEXT

    pm = re.search(r"\(([^)]*)\)\s*$", rest)
    if pm:
        label = rest[: pm.start()].strip()
        hint = pm.group(1).strip()
        if "required" in hint.lower():
            required = True
        ft, choices_text = _hint_to_type_and_choices(hint)

    hm = re.match(r"^(.+?)\s*[—\-–]\s*(.+)$", label)
    if hm and not pm:
        maybe_label, maybe_help = hm.group(1).strip(), hm.group(2).strip()
        if len(maybe_help) < 200 and not maybe_help.startswith("("):
            label, help_text = maybe_label, maybe_help

    label = label.strip() or "Untitled field"
    return FormFieldSpec(
        name="",
        label=label[:255],
        field_type=ft,
        required=required,
        help_text=help_text[:500],
        choices_text=choices_text,
    )


def _looks_like_field_line(line: str) -> bool:
    return bool(re.match(r"^\s*([-*•]|\d+[\.)])\s+\S", line))


def _spec_from_dict(data: dict[str, Any], warnings: list[str]) -> ParsedFormSpec:
    title = (data.get("title") or "").strip() or "Untitled form"
    desc = (data.get("description") or data.get("about") or "").strip()
    slug = (data.get("slug") or "").strip()
    raw_fields = data.get("fields") or data.get("questions") or []
    if not isinstance(raw_fields, list):
        raise FormEngineError("JSON must include a 'fields' array.")

    fields: list[FormFieldSpec] = []
    for i, item in enumerate(raw_fields):
        if isinstance(item, str):
            item = {"label": item.strip(), "field_type": FieldType.TEXT}
        if not isinstance(item, dict):
            warnings.append(f"Skipped invalid field entry #{i + 1}.")
            continue
        label = (item.get("label") or item.get("name") or item.get("title") or "").strip()
        if not label:
            warnings.append(f"Skipped field #{i + 1} (missing label).")
            continue
        ft = _normalize_field_type(item.get("field_type") or item.get("type"))
        req = bool(item.get("required") or item.get("is_required"))
        help_text = str(item.get("help_text") or item.get("description") or "")[:500]
        choices = item.get("choices") or item.get("options")
        if isinstance(choices, list):
            choices_text = "\n".join(str(c).strip() for c in choices if str(c).strip())
        else:
            choices_text = str(item.get("choices_text") or "").strip()
        if ft in (FieldType.SELECT, FieldType.RADIO, FieldType.CHECKLIST) and not choices_text.strip():
            choices_text = "Yes\nNo"
            warnings.append(f"Field “{label}”: added default choices for {ft}.")
        ph = str(item.get("placeholder") or "")[:255]
        fields.append(
            FormFieldSpec(
                name="",
                label=label[:255],
                field_type=ft,
                required=req,
                help_text=help_text,
                choices_text=choices_text,
                placeholder=ph,
            )
        )

    if not fields:
        raise FormEngineError("No valid fields found in the JSON payload.")

    names = _unique_field_names([f.label for f in fields])
    for f, n in zip(fields, names, strict=True):
        f.name = n

    return ParsedFormSpec(title=title[:255], description=desc, slug=slug[:120], fields=fields)


def _heuristic_parse(text: str, warnings: list[str]) -> ParsedFormSpec:
    raw = text.strip()
    if not raw:
        raise FormEngineError("Description is empty.")

    jd = _try_extract_json_dict(raw)
    if jd:
        try:
            return _spec_from_dict(jd, warnings)
        except FormEngineError:
            warnings.append("Found a JSON-like block but it was invalid; trying line-based parsing.")

    lines = [ln.rstrip() for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln.strip()]

    field_lines: list[str] = []
    title = ""
    desc_lines: list[str] = []

    marker_idx = None
    for i, ln in enumerate(lines):
        if re.match(r"^(fields?|questions?|field list)\s*:\s*$", ln, re.I):
            marker_idx = i
            break
    if marker_idx is not None:
        head = lines[:marker_idx]
        field_lines = [ln for ln in lines[marker_idx + 1 :] if _looks_like_field_line(ln)]
        title = head[0].strip() if head else "Untitled form"
        desc_lines = head[1:] if len(head) > 1 else []
    else:
        fi = [i for i, ln in enumerate(lines) if _looks_like_field_line(ln)]
        if fi:
            first = fi[0]
            if first > 0:
                title = lines[0].strip()
                desc_lines = lines[1:first] if first > 1 else []
            else:
                title = "Untitled form"
                desc_lines = []
            field_lines = [lines[i] for i in fi]
        else:
            title = lines[0].strip() if lines else "Untitled form"
            desc_lines = lines[1:]

    fields: list[FormFieldSpec] = []
    for ln in field_lines:
        spec = _parse_field_line(ln)
        if spec:
            fields.append(spec)

    if not fields and len(lines) >= 2:
        tail = " ".join(lines[1:])
        if "," in tail and len(tail) < 400:
            parts = [p.strip() for p in tail.split(",") if p.strip()]
            if len(parts) >= 2:
                warnings.append("No bullet list found; split the second line on commas for fields.")
                for p in parts:
                    fields.append(
                        FormFieldSpec(
                            name="",
                            label=p[:255],
                            field_type=FieldType.TEXT,
                            required=False,
                        )
                    )

    if not fields:
        raise FormEngineError(
            "Could not detect any fields. Use a list like:\n"
            "- Full name (text, required)\n"
            "- Work email (email)\n"
            "Or paste JSON with \"title\" and \"fields\"."
        )

    names = _unique_field_names([f.label for f in fields])
    for f, n in zip(fields, names, strict=True):
        f.name = n

    description = "\n".join(desc_lines).strip()
    return ParsedFormSpec(
        title=title[:255] or "Untitled form",
        description=description,
        slug="",
        fields=fields,
    )


def _openai_parse(text: str, warnings: list[str]) -> ParsedFormSpec | None:
    key = getattr(settings, "OPENAI_API_KEY", "")
    if not key:
        return None

    model = getattr(settings, "MAGIFORM_TEXT_TO_FORM_MODEL", "gpt-4o-mini")
    base = getattr(settings, "OPENAI_API_BASE", "https://api.openai.com/v1")

    schema_hint = json.dumps(
        {
            "title": "string",
            "description": "string (optional)",
            "slug": "string optional slug a-z0-9-",
            "fields": [
                {
                    "label": "string",
                    "field_type": "one of: text, textarea, email, number, date, select, radio, checkbox, checklist, file",
                    "required": "boolean",
                    "help_text": "string optional",
                    "choices": ["for select, radio, and checklist"],
                }
            ],
        }
    )

    system = (
        "You convert form descriptions into JSON only. No markdown, no prose. "
        "field_type must be one of: text, textarea, email, number, date, select, radio, checkbox, checklist, file. "
        "For select, radio, and checklist, always include a non-empty choices array of strings. "
        f"Schema example: {schema_hint}"
    )

    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text[:12000]},
        ],
        "temperature": 0.2,
    }

    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
        except Exception:
            raw = ""
        from .openai_client import format_openai_exception

        warnings.append(format_openai_exception(e, http_body=raw))
        return None
    except Exception as exc:
        from .openai_client import format_openai_exception

        warnings.append(format_openai_exception(exc))
        return None

    try:
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        warnings.append(f"Unexpected OpenAI response shape: {exc}")
        return None

    if not isinstance(data, dict):
        warnings.append("OpenAI returned non-object JSON.")
        return None

    return _spec_from_dict(data, warnings)


def parse_text_to_form_spec(description: str) -> tuple[ParsedFormSpec, list[str], str]:
    """
    Parse free-form text into a :class:`ParsedFormSpec`.

    Returns ``(spec, warnings, backend_label)`` where ``backend_label`` is
    ``"openai"``, ``"heuristic"``, or ``"openai+fallback"``.
    """
    warnings: list[str] = []
    text = (description or "").strip()
    if not text:
        raise FormEngineError("Description is empty.")

    had_openai_key = bool(getattr(settings, "OPENAI_API_KEY", ""))
    spec = _openai_parse(text, warnings)
    if spec is not None:
        return spec, warnings, "openai"

    spec = _heuristic_parse(text, warnings)
    backend = "openai+fallback" if had_openai_key else "heuristic"
    return spec, warnings, backend


def persist_parsed_form_spec(spec: ParsedFormSpec, user, entity: Entity) -> Form:
    """Create Form, FormField rows, and one default workflow step in a transaction."""
    if not spec.fields:
        raise FormEngineError("Nothing to save: no fields in spec.")

    slug = (spec.slug or "").strip()
    if slug:
        slug = slugify(slug)[:120].strip("-") or _unique_form_slug(spec.title, entity)
        if Form.objects.filter(entity=entity, slug=slug).exists():
            slug = _unique_form_slug(spec.title, entity)
    else:
        slug = _unique_form_slug(spec.title, entity)

    with transaction.atomic():
        form = Form.objects.create(
            entity=entity,
            title=spec.title[:255],
            slug=slug,
            description=spec.description,
            created_by=user if getattr(user, "is_authenticated", False) else None,
            is_published=False,
        )
        for i, fs in enumerate(spec.fields):
            ol = OptionsLayout.VERTICAL
            if fs.field_type == FieldType.RADIO:
                ol = OptionsLayout.HORIZONTAL
            elif fs.field_type == FieldType.CHECKLIST:
                ol = OptionsLayout.VERTICAL
            FormField.objects.create(
                form=form,
                order=i,
                field_type=fs.field_type,
                name=fs.name[:80],
                label=fs.label[:255],
                help_text=fs.help_text[:500],
                placeholder=fs.placeholder[:255],
                required=fs.required,
                choices_text=fs.choices_text[:10000] if fs.choices_text else "",
                options_layout=ol,
            )
        WorkflowStep.objects.create(
            form=form,
            order=0,
            slug="new",
            label="New",
            description="Initial step for new submissions.",
        )

    return form
