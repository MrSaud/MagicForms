"""Inbox AI assistant: natural-language search over the user's inbox scope."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from .entity_access import effective_entity_ids
from .inbox_filters import (
    ASSISTANT_WORKFLOW_STATES,
    INBOX_SORT_KEYS,
    apply_inbox_list_filters,
    annotate_has_unread_thread,
    field_snippets_for_submission,
    infer_date_range_from_text,
    infer_workflow_state_from_text,
    inbox_filter_options,
    normalize_assistant_keyword_q,
    parse_assistant_iso_date,
)
from .models import SubmissionUserTag
from django.db.models import Prefetch

from .models import FormSubmission, SubmissionEvent, SubmissionUserTag, SubmissionValue
from .openai_client import chat_completions_json, first_warning_message, openai_api_key
from .workflow_access import (
    assistant_search_list_queryset,
    inbox_submissions_filter_q,
    staff_workflow_thread_filter_q,
    staff_workflow_timeline_filter_q,
)


def inbox_ai_available() -> bool:
    return bool(openai_api_key())


def _inbox_ai_model() -> str:
    return getattr(settings, "MAGIFORM_INBOX_AI_MODEL", "") or getattr(
        settings, "MAGIFORM_TEXT_TO_FORM_MODEL", "gpt-4o-mini"
    )


def _assistant_search_context(forms, steps, fields, categories, user_tags) -> str:
    from .inbox_filters import _json_str as jstr

    form_lines = [
        f'  {{"id": {f.pk}, "title": "{jstr(f.entity.name)} — {jstr(f.title)}"}}'
        for f in forms[:80]
    ]
    step_lines = [
        f'  {{"id": {s.pk}, "form_id": {s.form_id}, "label": "{jstr(s.form.title)} — {jstr(s.label)}"}}'
        for s in steps[:120]
    ]
    field_lines = [
        f'  {{"form_id": {ff.form_id}, "name": "{jstr(ff.name)}", "label": "{jstr(ff.label)}", "type": "{jstr(ff.field_type)}"}}'
        for ff in fields[:200]
    ]
    cat_lines = [f'  {{"id": {c.pk}, "name": "{jstr(c.name)}"}}' for c in categories[:40]]
    tag_lines = [f'  "{jstr(t)}"' for t in user_tags[:60]]
    parts = [
        "Forms (form_id):\n[\n" + ",\n".join(form_lines) + "\n]",
        "Workflow steps (step_id):\n[\n" + ",\n".join(step_lines) + "\n]",
        "Form fields (field_name — searches answers & labels):\n[\n" + ",\n".join(field_lines) + "\n]",
    ]
    if cat_lines:
        parts.append("Categories / topics (category id):\n[\n" + ",\n".join(cat_lines) + "\n]")
    if tag_lines:
        parts.append("User private tags (tag exact match):\n[\n" + ",\n".join(tag_lines) + "\n]")
    return "\n\n".join(parts)


def _coerce_workflow_state(raw) -> str | None:
    wf = str(raw or "").strip()
    return wf if wf in ASSISTANT_WORKFLOW_STATES else None


def _finalize_assistant_plan(plan: dict[str, Any], question: str) -> dict[str, Any]:
    """Ensure status/date tokens become filters, not keyword q."""
    wf = _coerce_workflow_state(plan.get("workflow_state"))
    if not wf:
        wf = infer_workflow_state_from_text(question)
    if not wf and plan.get("q"):
        wf = infer_workflow_state_from_text(str(plan["q"]))
    plan["workflow_state"] = wf

    d_from = parse_assistant_iso_date(plan.get("submitted_from"))
    d_to = parse_assistant_iso_date(plan.get("submitted_to"))
    date_field = str(plan.get("date_field") or "").strip()
    if date_field not in ("submitted_at", "updated_at"):
        date_field = ""
    if not d_from and not d_to:
        d_from, d_to, inferred_field = infer_date_range_from_text(question)
        if not date_field:
            date_field = inferred_field
    if not date_field:
        date_field = "submitted_at"
    if d_from and d_to and d_from > d_to:
        d_from, d_to = d_to, d_from
    plan["submitted_from"] = d_from.isoformat() if d_from else None
    plan["submitted_to"] = d_to.isoformat() if d_to else None
    plan["date_field"] = date_field

    tag_raw = str(plan.get("tag") or "").strip()
    if tag_raw:
        plan["tag"] = SubmissionUserTag.normalize_label(tag_raw) or None
    else:
        plan["tag"] = None

    field_name = str(plan.get("field_name") or "").strip()
    plan["field_name"] = field_name or None

    raw_cat = plan.get("category_id")
    if isinstance(raw_cat, int):
        plan["category_id"] = raw_cat
    elif isinstance(raw_cat, str) and raw_cat.isdigit():
        plan["category_id"] = int(raw_cat)
    else:
        plan["category_id"] = None

    keyword_source = str(plan.get("q") or question or "")
    plan["q"] = normalize_assistant_keyword_q(
        keyword_source,
        wf,
        date_from=d_from,
        date_to=d_to,
    )
    return plan


def parse_inbox_question(
    question: str,
    *,
    forms,
    steps,
    fields,
    categories,
    user_tags,
    field_names: set[str],
    warnings: list[str],
) -> dict[str, Any]:
    """Turn a user question into filter plan: q, form_id, step_id, workflow_state, sort, reply."""
    q = (question or "").strip()
    plan: dict[str, Any] = {
        "q": "",
        "form_id": None,
        "step_id": None,
        "workflow_state": None,
        "submitted_from": None,
        "submitted_to": None,
        "date_field": "submitted_at",
        "tag": None,
        "field_name": None,
        "category_id": None,
        "sort": "submitted_at_desc",
        "reply": "",
    }
    if not q:
        return plan

    valid_form_ids = {f.pk for f in forms}
    valid_step_ids = {s.pk for s in steps}
    valid_category_ids = {c.pk for c in categories}
    valid_tags = set(user_tags)

    today_iso = timezone.localdate().isoformat()
    schema = json.dumps(
        {
            "q": "optional — matches answers, field labels, form title, email, reference, category name, tags",
            "form_id": "integer or null — must be from forms list",
            "step_id": "integer or null — must be from steps list",
            "workflow_state": "null or one of: in_progress, completed, rejected",
            "submitted_from": "YYYY-MM-DD or null",
            "submitted_to": "YYYY-MM-DD or null",
            "date_field": "submitted_at or updated_at",
            "field_name": "internal field name from catalog or null — narrow search to that answer",
            "tag": "exact user private tag string from catalog or null",
            "category_id": "integer category/topic id or null",
            "sort": "submitted_at_desc, submitted_at_asc, updated_at_desc, updated_at_asc, form_title, form_title_desc",
            "reply": "one short sentence explaining what you searched (plain language, no JSON)",
        }
    )
    system = (
        "You help a user search submissions connected to them: as applicant (they submitted), "
        "as current-step assignee/delegate, or anywhere they participated on the workflow timeline or thread. "
        f"Today's date is {today_iso} in the server timezone. "
        "Return JSON only. Search covers submitted form field values and labels, status, dates, categories/topics, and private tags. "
        "Pick form_id/step_id/field_name/tag/category_id only from the catalogs below. "
        "When they ask for rejected/denied set workflow_state rejected (not in q). "
        "completed → workflow_state completed. pending/in-progress → in_progress. "
        "For dates set submitted_from/submitted_to; do not put date words in q. "
        "Use field_name when they name a specific form field (e.g. civil ID, TOEFL score). "
        "Use tag for their private labels. Use category_id for topic/category. "
        "Put free-text search terms in q (answers, emails, names). "
        f"Schema: {schema}\n\n{_assistant_search_context(forms, steps, fields, categories, user_tags)}"
    )

    data = chat_completions_json(
        system=system,
        user_msg=q,
        model=_inbox_ai_model(),
        warnings=warnings,
        timeout=45,
    )
    if data:
        plan["q"] = str(data.get("q") or "").strip()[:200]
        plan["workflow_state"] = _coerce_workflow_state(data.get("workflow_state"))
        plan["submitted_from"] = data.get("submitted_from")
        plan["submitted_to"] = data.get("submitted_to")
        raw_df = str(data.get("date_field") or "").strip()
        if raw_df in ("submitted_at", "updated_at"):
            plan["date_field"] = raw_df
        raw_fn = str(data.get("field_name") or "").strip()
        if raw_fn in field_names:
            plan["field_name"] = raw_fn
        raw_tag = str(data.get("tag") or "").strip()
        if raw_tag in valid_tags:
            plan["tag"] = raw_tag
        raw_cat = data.get("category_id")
        if isinstance(raw_cat, int) and raw_cat in valid_category_ids:
            plan["category_id"] = raw_cat
        elif isinstance(raw_cat, str) and raw_cat.isdigit() and int(raw_cat) in valid_category_ids:
            plan["category_id"] = int(raw_cat)
        raw_fid = data.get("form_id")
        if isinstance(raw_fid, int) and raw_fid in valid_form_ids:
            plan["form_id"] = raw_fid
        elif isinstance(raw_fid, str) and raw_fid.isdigit() and int(raw_fid) in valid_form_ids:
            plan["form_id"] = int(raw_fid)
        raw_sid = data.get("step_id")
        if isinstance(raw_sid, int) and raw_sid in valid_step_ids:
            plan["step_id"] = raw_sid
        elif isinstance(raw_sid, str) and raw_sid.isdigit() and int(raw_sid) in valid_step_ids:
            plan["step_id"] = int(raw_sid)
        sort = str(data.get("sort") or "").strip()
        if sort in INBOX_SORT_KEYS:
            plan["sort"] = sort
        plan["reply"] = str(data.get("reply") or "").strip()[:500]
        return _finalize_assistant_plan(plan, q)

    plan["reply"] = _("Searching your connected submissions for matching keywords.")
    return _finalize_assistant_plan(plan, q)


def _fake_request_with_plan(plan: dict[str, Any]):
    """Minimal request-like object for apply_inbox_list_filters."""

    class _R:
        GET = {
            "q": plan.get("q") or "",
            "form": str(plan["form_id"]) if plan.get("form_id") else "",
            "step": str(plan["step_id"]) if plan.get("step_id") else "",
            "workflow_state": plan.get("workflow_state") or "",
            "submitted_from": plan.get("submitted_from") or "",
            "submitted_to": plan.get("submitted_to") or "",
            "date_field": plan.get("date_field") or "submitted_at",
            "tag": plan.get("tag") or "",
            "field_name": plan.get("field_name") or "",
            "category": str(plan["category_id"]) if plan.get("category_id") else "",
            "sort": plan.get("sort") or "submitted_at_desc",
        }

    return _R()


def _assistant_role_label_sets(user, request, submission_pks: list[int]) -> tuple[set[int], set[int], set[int]]:
    """Assignee, timeline, and thread submission pk sets for role badges."""
    if not submission_pks:
        return set(), set(), set()
    eids = effective_entity_ids(user, request)
    assignee_pks = set(
        FormSubmission.objects.filter(pk__in=submission_pks)
        .filter(inbox_submissions_filter_q(user, eids))
        .values_list("pk", flat=True)
    )
    kinds = (
        SubmissionEvent.Kind.STEP_APPROVED,
        SubmissionEvent.Kind.STEP_CHANGED,
        SubmissionEvent.Kind.WORKFLOW_COMPLETED,
        SubmissionEvent.Kind.WORKFLOW_REJECTED,
        SubmissionEvent.Kind.APPROVE_UNDONE,
        SubmissionEvent.Kind.NOTE,
        SubmissionEvent.Kind.FORWARDED,
        SubmissionEvent.Kind.ATTACHMENT_ADDED,
    )
    timeline_pks = set(
        SubmissionEvent.objects.filter(
            submission_id__in=submission_pks,
            created_by=user,
            kind__in=kinds,
        ).values_list("submission_id", flat=True)
    )
    thread_pks = set(
        FormSubmission.objects.filter(pk__in=submission_pks)
        .filter(staff_workflow_thread_filter_q(user, eids))
        .values_list("pk", flat=True)
    )
    return assignee_pks, timeline_pks, thread_pks


def _role_labels_for_row(
    user,
    submission,
    *,
    assignee_pks: set[int],
    timeline_pks: set[int],
    thread_pks: set[int],
) -> list[str]:
    roles: list[str] = []
    if submission.submitted_by_id == user.pk:
        roles.append(_("Applicant"))
    else:
        ue = (getattr(user, "email", None) or "").strip().lower()
        se = (submission.submitter_email or "").strip().lower()
        if ue and se and ue == se:
            roles.append(_("Applicant (email)"))
    if submission.pk in assignee_pks:
        roles.append(_("Assignee"))
    if submission.pk in timeline_pks:
        roles.append(_("Workflow"))
    if submission.pk in thread_pks and submission.pk not in timeline_pks:
        roles.append(_("Thread"))
    return roles


def search_inbox_submissions(user, request, plan: dict[str, Any], *, limit: int = 25) -> tuple[list[dict], int]:
    opts = inbox_filter_options(user, request)
    search_q = (plan.get("q") or "").strip()
    qs = annotate_has_unread_thread(
        assistant_search_list_queryset(user, request)
        .select_related("form", "form__entity", "form__category", "current_step", "submitted_by")
        .prefetch_related(
            Prefetch(
                "values",
                queryset=SubmissionValue.objects.select_related("field").order_by("field__order", "field_id"),
            ),
            Prefetch(
                "user_tags",
                queryset=SubmissionUserTag.objects.filter(user=user).order_by("label"),
                to_attr="_prefetched_user_tags",
            ),
        ),
        user,
    )
    fake = _fake_request_with_plan(plan)
    qs, _meta = apply_inbox_list_filters(
        qs,
        fake,
        inbox_form_ids=opts["inbox_form_ids"],
        user=user,
        valid_field_names=opts["field_names"],
    )
    total = qs.count()
    rows = list(qs[:limit])
    assignee_pks, timeline_pks, thread_pks = _assistant_role_label_sets(
        user, request, [s.pk for s in rows]
    )
    results = []
    for s in rows:
        manage_url = reverse(
            "manage:submission_manage_detail",
            kwargs={"pk": s.form_id, "submission_id": s.pk},
        )
        pr_tags = getattr(s, "_prefetched_user_tags", None)
        tag_labels = [t.label for t in pr_tags] if pr_tags else []
        category_name = s.form.category.name if getattr(s.form, "category_id", None) and s.form.category else ""
        results.append(
            {
                "id": s.pk,
                "form_id": s.form_id,
                "reference": s.reference_token,
                "form_title": s.form.title,
                "entity_name": s.form.entity.name,
                "category_name": category_name,
                "step_label": s.current_step.label if s.current_step else "",
                "workflow_state": s.workflow_state,
                "submitter_email": (s.submitter_email or "").strip(),
                "submitted_at": timezone.localtime(s.submitted_at).isoformat(),
                "submitted_display": timezone.localtime(s.submitted_at).strftime("%b %d, %Y %H:%M"),
                "updated_display": timezone.localtime(s.updated_at).strftime("%b %d, %Y %H:%M"),
                "manage_url": manage_url,
                "has_unread_thread": bool(getattr(s, "has_unread_thread", False)),
                "role_labels": _role_labels_for_row(
                    user,
                    s,
                    assignee_pks=assignee_pks,
                    timeline_pks=timeline_pks,
                    thread_pks=thread_pks,
                ),
                "tag_labels": tag_labels,
                "field_snippets": field_snippets_for_submission(s, search_q),
            }
        )
    return results, total


def run_inbox_ai_chat(user, request, question: str) -> dict[str, Any]:
    warnings: list[str] = []
    opts = inbox_filter_options(user, request)
    plan = parse_inbox_question(
        question,
        forms=opts["forms"],
        steps=opts["steps"],
        fields=opts["fields"],
        categories=opts["categories"],
        user_tags=opts["user_tags"],
        field_names=opts["field_names"],
        warnings=warnings,
    )
    results, total = search_inbox_submissions(user, request, plan, limit=25)
    used_openai = inbox_ai_available() and not warnings
    backend = "openai" if used_openai else "keyword"
    openai_message = first_warning_message(warnings)
    reply = plan.get("reply") or ""
    if not reply:
        if results:
            reply = _("Found %(n)s submission(s) you can open below.") % {"n": len(results)}
            if total > len(results):
                reply += " " + _("Showing the first %(n)s.") % {"n": len(results)}
        else:
            reply = _("No connected submissions matched that question. Try different keywords or filters.")

    apply_filters_url = reverse("manage:submission_search")
    params = ["relation=any"]
    if plan.get("q"):
        params.append(f"q={urllib.parse.quote(plan['q'])}")
    if plan.get("form_id"):
        params.append(f"form={plan['form_id']}")
    if plan.get("workflow_state"):
        params.append(f"workflow_state={plan['workflow_state']}")
    if plan.get("submitted_from"):
        params.append(f"submitted_from={plan['submitted_from']}")
    if plan.get("submitted_to"):
        params.append(f"submitted_to={plan['submitted_to']}")
    if plan.get("tag"):
        params.append(f"tag={urllib.parse.quote(plan['tag'])}")
    if plan.get("field_name"):
        params.append(f"field_name={urllib.parse.quote(plan['field_name'])}")
    if plan.get("category_id"):
        params.append(f"category={plan['category_id']}")
    if plan.get("sort") and plan["sort"] != "submitted_at_desc":
        params.append(f"sort={plan['sort']}")
    if params:
        apply_filters_url += "?" + "&".join(params)

    return {
        "ok": True,
        "reply": reply,
        "results": results,
        "total_count": total,
        "plan": {
            "q": plan.get("q") or "",
            "form_id": plan.get("form_id"),
            "step_id": plan.get("step_id"),
            "workflow_state": plan.get("workflow_state"),
            "submitted_from": plan.get("submitted_from"),
            "submitted_to": plan.get("submitted_to"),
            "date_field": plan.get("date_field"),
            "tag": plan.get("tag"),
            "field_name": plan.get("field_name"),
            "category_id": plan.get("category_id"),
            "sort": plan.get("sort"),
        },
        "apply_filters_url": apply_filters_url,
        "ai_available": inbox_ai_available(),
        "backend": backend,
        "openai_message": openai_message,
        "openai_used": used_openai,
        "warnings": warnings[:3],
    }
