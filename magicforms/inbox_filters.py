"""Shared inbox list filtering (studio inbox view and AI assistant)."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from .opaque_ids import parse_id as oid_parse
from django.db.models import BigIntegerField, Exists, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone
from django.db.models.functions import Coalesce

from .models import (
    Form,
    FormCategory,
    FormField,
    FormSubmission,
    SubmissionThreadLastRead,
    SubmissionThreadMessage,
    SubmissionUserTag,
    WorkflowStep,
)

_THREAD_READ_ZERO = 0


def annotate_has_unread_thread(qs: QuerySet, user) -> QuerySet:
    """Annotate ``has_unread_thread`` for inbox list rows."""
    seen_sq = SubmissionThreadLastRead.objects.filter(
        user=user,
        submission_id=OuterRef("pk"),
    ).values("last_seen_message_id")[:1]
    return qs.annotate(
        has_unread_thread=Exists(
            SubmissionThreadMessage.objects.filter(
                submission_id=OuterRef("pk"),
            )
            .exclude(author=user)
            .filter(
                pk__gt=Coalesce(Subquery(seen_sq, output_field=BigIntegerField(null=True)), _THREAD_READ_ZERO)
            )
        )
    )


INBOX_SORT_KEYS = frozenset(
    {
        "submitted_at_desc",
        "submitted_at_asc",
        "updated_at_desc",
        "updated_at_asc",
        "form_title",
        "form_title_desc",
    }
)

ASSISTANT_WORKFLOW_STATES = frozenset(
    {
        "in_progress",
        "completed",
        "rejected",
    }
)

# Words that mean workflow status, not form-title keywords (see submission search).
_WORKFLOW_STATUS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(rejected|reject|denied|declined|refused)\b", re.I), "rejected"),
    (re.compile(r"\b(completed|approved|accepted|finished)\b", re.I), "completed"),
    (re.compile(r"\b(in\s+progress|pending|open|active)\b", re.I), "in_progress"),
)

_ASSISTANT_NOISE_WORDS = re.compile(
    r"\b(forms?|submissions?|requests?|applications?|my|me|show|find|list|all|any|the|status|with)\b",
    re.I,
)

_ASSISTANT_DATE_FIELD_KEYS = frozenset({"submitted_at", "updated_at"})

_ISO_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_DATE_RANGE_RE = re.compile(
    r"(20\d{2}-\d{2}-\d{2})\s*(?:to|through|until|and|–|-)\s*(20\d{2}-\d{2}-\d{2})",
    re.I,
)
_SINCE_DATE_RE = re.compile(r"\bsince\s+(20\d{2}-\d{2}-\d{2})\b", re.I)
_BEFORE_DATE_RE = re.compile(r"\bbefore\s+(20\d{2}-\d{2}-\d{2})\b", re.I)
_AFTER_DATE_RE = re.compile(r"\b(?:after|from)\s+(20\d{2}-\d{2}-\d{2})\b", re.I)
_ON_DATE_RE = re.compile(r"\bon\s+(20\d{2}-\d{2}-\d{2})\b", re.I)
_IN_YEAR_RE = re.compile(r"\bin\s+(20\d{2})\b")
_LAST_N_DAYS_RE = re.compile(r"\b(?:last|past)\s+(\d{1,3})\s+days?\b", re.I)
_LAST_N_MONTHS_RE = re.compile(r"\b(?:last|past)\s+(\d{1,2})\s+months?\b", re.I)

_DATE_PHRASE_NOISE = re.compile(
    r"\b(?:today|yesterday|last|past|this|week|month|months?|days?|recent(?:ly)?|"
    r"since|before|after|between|from|to|until|through|on|in|ago|submitted|updated|modified|"
    r"january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.I,
)


def parse_assistant_iso_date(raw: str | None) -> date | None:
    s = (raw or "").strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _assistant_date_field_from_text(text: str) -> str:
    if re.search(r"\b(updated|modified|changed|activity)\b", text or "", re.I):
        return "updated_at"
    return "submitted_at"


def infer_date_range_from_text(text: str, *, today: date | None = None) -> tuple[date | None, date | None, str]:
    """
    Parse relative/absolute dates from a question.

    Returns ``(from_date, to_date, date_field)`` where ``date_field`` is
    ``submitted_at`` or ``updated_at``.
    """
    t = text or ""
    today = today or timezone.localdate()
    field = _assistant_date_field_from_text(t)

    m = _DATE_RANGE_RE.search(t)
    if m:
        d1 = parse_assistant_iso_date(m.group(1))
        d2 = parse_assistant_iso_date(m.group(2))
        if d1 and d2:
            return (min(d1, d2), max(d1, d2), field)

    m = _SINCE_DATE_RE.search(t)
    if m:
        d1 = parse_assistant_iso_date(m.group(1))
        if d1:
            return (d1, today, field)

    m = _BEFORE_DATE_RE.search(t)
    if m:
        d1 = parse_assistant_iso_date(m.group(1))
        if d1:
            return (None, d1 - timedelta(days=1), field)

    m = _AFTER_DATE_RE.search(t)
    if m:
        d1 = parse_assistant_iso_date(m.group(1))
        if d1:
            return (d1, today, field)

    m = _IN_YEAR_RE.search(t)
    if m:
        year = int(m.group(1))
        if 2000 <= year <= 2100:
            return (date(year, 1, 1), date(year, 12, 31), field)

    m = _ON_DATE_RE.search(t)
    if m:
        d1 = parse_assistant_iso_date(m.group(1))
        if d1:
            return (d1, d1, field)

    iso_hits = _ISO_DATE_RE.findall(t)
    if len(iso_hits) == 1:
        d1 = parse_assistant_iso_date(iso_hits[0])
        if d1:
            return (d1, d1, field)

    low = t.lower()
    if re.search(r"\btoday\b", low):
        return (today, today, field)
    if re.search(r"\byesterday\b", low):
        d = today - timedelta(days=1)
        return (d, d, field)

    m = _LAST_N_DAYS_RE.search(t)
    if m:
        n = max(1, min(int(m.group(1)), 366))
        return (today - timedelta(days=n - 1), today, field)

    if re.search(r"\b(?:last|past)\s+week\b", low):
        return (today - timedelta(days=6), today, field)

    if re.search(r"\bthis\s+week\b", low):
        return (today - timedelta(days=today.weekday()), today, field)

    if re.search(r"\b(?:last|past)\s+month\b", low):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return (last_prev.replace(day=1), last_prev, field)

    if re.search(r"\bthis\s+month\b", low):
        return (today.replace(day=1), today, field)

    m = _LAST_N_MONTHS_RE.search(t)
    if m:
        n = max(1, min(int(m.group(1)), 24))
        start = today - timedelta(days=30 * n)
        return (start, today, field)

    return (None, None, field)


def strip_date_phrases(text: str) -> str:
    """Remove date phrases so they are not used as keyword ``q``."""
    out = _DATE_RANGE_RE.sub(" ", text or "")
    out = _SINCE_DATE_RE.sub(" ", out)
    out = _BEFORE_DATE_RE.sub(" ", out)
    out = _AFTER_DATE_RE.sub(" ", out)
    out = _ON_DATE_RE.sub(" ", out)
    out = _IN_YEAR_RE.sub(" ", out)
    out = _ISO_DATE_RE.sub(" ", out)
    out = _DATE_PHRASE_NOISE.sub(" ", out)
    return " ".join(out.split())


def apply_assistant_date_filter(
    qs: QuerySet,
    d_from: date | None,
    d_to: date | None,
    *,
    date_field: str = "submitted_at",
) -> QuerySet:
    field = date_field if date_field in _ASSISTANT_DATE_FIELD_KEYS else "submitted_at"
    if d_from is not None:
        qs = qs.filter(**{f"{field}__date__gte": d_from})
    if d_to is not None:
        qs = qs.filter(**{f"{field}__date__lte": d_to})
    return qs


def normalize_assistant_keyword_q(
    question: str,
    workflow_state: str | None = None,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> str:
    """Build keyword ``q`` after extracting status and date filters."""
    out = question or ""
    if workflow_state:
        out = strip_workflow_status_words(out)
    if date_from is not None or date_to is not None:
        out = strip_date_phrases(out)
    out = _ASSISTANT_NOISE_WORDS.sub(" ", out)
    return " ".join(out.split())[:200]


def infer_workflow_state_from_text(text: str) -> str | None:
    """Map natural language to ``FormSubmission.workflow_state`` value."""
    for pattern, state in _WORKFLOW_STATUS_PATTERNS:
        if pattern.search(text or ""):
            return state
    return None


def strip_workflow_status_words(text: str) -> str:
    """Remove status tokens so ``q`` does not require them in form titles."""
    out = text or ""
    for pattern, _state in _WORKFLOW_STATUS_PATTERNS:
        out = pattern.sub(" ", out)
    out = _ASSISTANT_NOISE_WORDS.sub(" ", out)
    return " ".join(out.split())


def _json_str(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def build_assistant_keyword_q(search_q: str, user) -> Q:
    """
    Match submission metadata and answers: form, entity, category, step, applicant,
    reference, field labels/names/values, and the user's private tags.
    """
    q_kw = (
        Q(form__title__icontains=search_q)
        | Q(form__slug__icontains=search_q)
        | Q(form__entity__name__icontains=search_q)
        | Q(form__category__name__icontains=search_q)
        | Q(submitter_email__icontains=search_q)
        | Q(submitted_by__username__icontains=search_q)
        | Q(submitted_by__email__icontains=search_q)
        | Q(current_step__label__icontains=search_q)
        | Q(values__value__icontains=search_q)
        | Q(values__field__label__icontains=search_q)
        | Q(values__field__name__icontains=search_q)
    )
    if search_q.isdigit() and len(search_q) >= 6:
        if len(search_q) in (14, 16):
            q_kw |= Q(reference_token=search_q)
        else:
            q_kw |= Q(reference_token__startswith=search_q)
    if user is not None and getattr(user, "is_authenticated", False):
        q_kw |= Q(user_tags__user=user, user_tags__label__icontains=search_q)
    return q_kw


def field_snippets_for_submission(submission, search_q: str, *, limit: int = 5) -> list[dict[str, str]]:
    """Short field label/value pairs that matched ``search_q`` (for AI result cards)."""
    if not (search_q or "").strip():
        return []
    qlow = search_q.lower()
    out: list[dict[str, str]] = []
    for sv in submission.values.all():
        val = (sv.value or "").strip()
        label = sv.field.label
        name = sv.field.name
        hit = (
            qlow in val.lower()
            or qlow in label.lower()
            or qlow in name.lower()
        )
        if not hit:
            continue
        if sv.attachment:
            display = val or "(file attached)"
        else:
            display = val[:140] + ("…" if len(val) > 140 else "")
        out.append({"label": label, "name": name, "value": display})
        if len(out) >= limit:
            break
    return out


INBOX_ORDER_MAP = {
    "submitted_at_desc": ("-submitted_at",),
    "submitted_at_asc": ("submitted_at",),
    "updated_at_desc": ("-updated_at",),
    "updated_at_asc": ("updated_at",),
    "form_title": ("form__title", "-submitted_at"),
    "form_title_desc": ("-form__title", "-submitted_at"),
}


def apply_inbox_list_filters(
    qs: QuerySet,
    request,
    *,
    inbox_form_ids: set[int],
    user=None,
    valid_field_names: set[str] | None = None,
) -> tuple[QuerySet, dict[str, Any]]:
    """
    Apply GET-style inbox filters from ``request`` (also used for AI search plans).

    Returns ``(queryset, meta)`` with keys: search_q, form_filter_id, step_filter_id,
    workflow_state, submitted_from, submitted_to, date_field, sort_key, has_filters.
    """
    meta: dict[str, Any] = {
        "search_q": "",
        "form_filter_id": None,
        "step_filter_id": None,
        "workflow_state": "",
        "submitted_from": "",
        "submitted_to": "",
        "date_field": "submitted_at",
        "tag": "",
        "field_name": "",
        "category_id": None,
        "sort_key": "submitted_at_desc",
        "has_filters": False,
    }
    field_names = valid_field_names or set()

    form_raw = (request.GET.get("form") or "").strip()
    if not form_raw and hasattr(request, "POST"):
        form_raw = (request.POST.get("form") or "").strip()
    form_filter_id = None
    fid = oid_parse(form_raw)
    if fid:
        if fid in inbox_form_ids:
            qs = qs.filter(form_id=fid)
            form_filter_id = fid
            meta["form_filter_id"] = fid

    search_q = (request.GET.get("q") or "").strip()[:200]
    if not search_q and hasattr(request, "POST"):
        search_q = (request.POST.get("q") or "").strip()[:200]
    meta["search_q"] = search_q

    field_name_raw = (request.GET.get("field_name") or "").strip()[:80]
    if not field_name_raw and hasattr(request, "POST"):
        field_name_raw = (request.POST.get("field_name") or "").strip()[:80]
    if field_name_raw and field_name_raw in field_names:
        meta["field_name"] = field_name_raw

    tag_raw = (request.GET.get("tag") or "").strip()[:80]
    if not tag_raw and hasattr(request, "POST"):
        tag_raw = (request.POST.get("tag") or "").strip()[:80]
    tag_label = ""
    if tag_raw and user is not None:
        tag_label = SubmissionUserTag.normalize_label(tag_raw) or ""
        if tag_label:
            meta["tag"] = tag_label
            qs = qs.filter(user_tags__user=user, user_tags__label=tag_label)

    cat_raw = (request.GET.get("category") or "").strip()
    if not cat_raw and hasattr(request, "POST"):
        cat_raw = (request.POST.get("category") or "").strip()
    if cat_raw.isdigit():
        cid = int(cat_raw)
        if FormCategory.objects.filter(
            pk=cid,
            forms__pk__in=inbox_form_ids,
            forms__deleted_at__isnull=True,
        ).exists():
            qs = qs.filter(form__category_id=cid)
            meta["category_id"] = cid

    if search_q:
        if meta["field_name"]:
            qs = qs.filter(
                values__field__name=meta["field_name"],
                values__value__icontains=search_q,
            ).distinct()
        else:
            qs = qs.filter(build_assistant_keyword_q(search_q, user)).distinct()

    step_raw = (request.GET.get("step") or "").strip()
    if not step_raw and hasattr(request, "POST"):
        step_raw = (request.POST.get("step") or "").strip()
    step_filter_id = None
    qs_before_step = qs
    sid = oid_parse(step_raw)
    if sid:
        if qs_before_step.filter(current_step_id=sid).exists():
            qs = qs.filter(current_step_id=sid)
            step_filter_id = sid
            meta["step_filter_id"] = sid

    wf = (request.GET.get("workflow_state") or "").strip()
    if not wf and hasattr(request, "POST"):
        wf = (request.POST.get("workflow_state") or "").strip()
    if wf in ASSISTANT_WORKFLOW_STATES:
        qs = qs.filter(workflow_state=wf)
        meta["workflow_state"] = wf

    d_from_raw = (request.GET.get("submitted_from") or "").strip()
    d_to_raw = (request.GET.get("submitted_to") or "").strip()
    if not d_from_raw and hasattr(request, "POST"):
        d_from_raw = (request.POST.get("submitted_from") or "").strip()
    if not d_to_raw and hasattr(request, "POST"):
        d_to_raw = (request.POST.get("submitted_to") or "").strip()
    d_from = parse_assistant_iso_date(d_from_raw)
    d_to = parse_assistant_iso_date(d_to_raw)
    date_field = (request.GET.get("date_field") or "submitted_at").strip()
    if date_field not in _ASSISTANT_DATE_FIELD_KEYS:
        date_field = "submitted_at"
    if d_from and d_to and d_from > d_to:
        d_from, d_to = d_to, d_from
    if d_from or d_to:
        qs = apply_assistant_date_filter(qs, d_from, d_to, date_field=date_field)
        if d_from:
            meta["submitted_from"] = d_from.isoformat()
        if d_to:
            meta["submitted_to"] = d_to.isoformat()
        meta["date_field"] = date_field

    sort_key = (request.GET.get("sort") or "submitted_at_desc").strip()
    if sort_key not in INBOX_SORT_KEYS:
        sort_key = "submitted_at_desc"
    meta["sort_key"] = sort_key
    qs = qs.order_by(*INBOX_ORDER_MAP[sort_key])

    meta["has_filters"] = bool(
        search_q
        or form_filter_id is not None
        or step_filter_id is not None
        or meta["workflow_state"]
        or meta["submitted_from"]
        or meta["submitted_to"]
        or meta["tag"]
        or meta["field_name"]
        or meta["category_id"] is not None
    )
    return qs, meta


def inbox_scope_form_ids(user, request) -> set[int]:
    from .workflow_access import assistant_search_list_queryset

    return set(assistant_search_list_queryset(user, request).values_list("form_id", flat=True))


def inbox_filter_options(user, request) -> dict[str, Any]:
    """Forms and steps available for inbox assistant filters / AI context."""
    from .workflow_access import assistant_search_list_queryset

    combined = assistant_search_list_queryset(user, request)
    inbox_form_ids = set(combined.values_list("form_id", flat=True))
    step_ids = (
        combined.exclude(current_step_id__isnull=True)
        .values_list("current_step_id", flat=True)
        .distinct()
    )
    forms = list(
        Form.objects.filter(pk__in=inbox_form_ids, deleted_at__isnull=True)
        .select_related("entity")
        .order_by("entity__name", "title")
    )
    steps = list(
        WorkflowStep.objects.filter(pk__in=step_ids)
        .select_related("form")
        .order_by("form__title", "order", "id")
    )
    fields = list(
        FormField.objects.filter(form_id__in=inbox_form_ids)
        .select_related("form")
        .order_by("form__title", "order", "id")[:250]
    )
    categories = list(
        FormCategory.objects.filter(forms__pk__in=inbox_form_ids)
        .distinct()
        .order_by("name")[:80]
    )
    field_names = {f.name for f in fields}
    user_tags = list(
        SubmissionUserTag.objects.filter(user=user)
        .values_list("label", flat=True)
        .distinct()
        .order_by("label")[:120]
    )
    return {
        "inbox_form_ids": inbox_form_ids,
        "forms": forms,
        "steps": steps,
        "fields": fields,
        "field_names": field_names,
        "categories": categories,
        "user_tags": user_tags,
    }
