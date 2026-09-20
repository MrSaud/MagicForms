"""Mobile API: search submissions related to the signed-in user."""

from __future__ import annotations

from django.db.models import Q

from django.http import HttpRequest

from magicforms.entity_access import effective_entity_ids, forms_queryset_for_user
from magicforms.models import FormSubmission, SubmissionEvent
from magicforms.workflow_access import (
    applicant_submissions_filter_q,
    inbox_submissions_filter_q,
    staff_workflow_thread_filter_q,
    staff_workflow_timeline_filter_q,
)

from .mobile_content import _mobile_request_user, serialize_inbox_item


def _search_relation_q(user, eids, relation: str) -> Q:
    q_applicant = applicant_submissions_filter_q(user)
    q_assignee = inbox_submissions_filter_q(user, eids)
    q_timeline = staff_workflow_timeline_filter_q(user, eids)
    q_thread = staff_workflow_thread_filter_q(user, eids)
    if relation == "applicant":
        return q_applicant
    if relation == "workflow":
        return q_assignee | q_timeline | q_thread
    return q_applicant | q_assignee | q_timeline | q_thread


def _search_role_labels(
    user,
    submission,
    *,
    assignee_pks: set[int],
    timeline_pks: set[int],
) -> list[str]:
    roles: list[str] = []
    if submission.submitted_by_id == user.pk:
        roles.append("Applicant")
    else:
        ue = (user.email or "").strip().lower()
        se = (submission.submitter_email or "").strip().lower()
        if ue and se and ue == se:
            roles.append("Applicant (email)")
    if submission.pk in assignee_pks:
        roles.append("Assignee")
    if submission.pk in timeline_pks:
        roles.append("Workflow")
    return roles


def submission_search_payload(
    request: HttpRequest,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    from magicforms.manage_views import _annotate_has_unread_thread

    user = _mobile_request_user(request)
    eids = effective_entity_ids(user, request)

    relation = (request.GET.get("relation") or "any").strip()
    if relation == "assignee":
        relation = "workflow"
    if relation not in ("any", "applicant", "workflow"):
        relation = "any"

    q_rel = _search_relation_q(user, eids, relation)
    qs = (
        FormSubmission.objects.filter(q_rel, form__deleted_at__isnull=True)
        .distinct()
        .select_related("form", "form__entity", "current_step", "submitted_by")
        .prefetch_related("current_step__assigned_users")
    )
    if eids is not None:
        qs = qs.filter(form__entity_id__in=eids)

    wf = (request.GET.get("workflow_state") or "").strip()
    if wf in (
        FormSubmission.WorkflowState.IN_PROGRESS,
        FormSubmission.WorkflowState.COMPLETED,
        FormSubmission.WorkflowState.REJECTED,
    ):
        qs = qs.filter(workflow_state=wf)

    form_raw = (request.GET.get("form") or "").strip()
    if form_raw.isdigit():
        fid = int(form_raw)
        if forms_queryset_for_user(user, request=request).filter(pk=fid).exists():
            qs = qs.filter(form_id=fid)

    search_q = (request.GET.get("q") or "").strip()[:200]
    if search_q:
        q_kw = (
            Q(form__title__icontains=search_q)
            | Q(form__slug__icontains=search_q)
            | Q(submitter_email__icontains=search_q)
            | Q(submitted_by__username__icontains=search_q)
            | Q(submitted_by__email__icontains=search_q)
        )
        if search_q.isdigit() and len(search_q) >= 6:
            if len(search_q) in (14, 16):
                q_kw |= Q(reference_token=search_q)
            else:
                q_kw |= Q(reference_token__startswith=search_q)
        qs = qs.filter(q_kw)

    sort_key = (request.GET.get("sort") or "submitted_at_desc").strip()
    order_map = {
        "submitted_at_desc": ("-submitted_at",),
        "submitted_at_asc": ("submitted_at",),
        "updated_at_desc": ("-updated_at",),
        "updated_at_asc": ("updated_at",),
        "form_title": ("form__title", "-submitted_at"),
    }
    if sort_key not in order_map:
        sort_key = "submitted_at_desc"
    qs = qs.order_by(*order_map[sort_key])

    total = qs.count()
    page = list(qs[offset : offset + limit])
    page_pks = [s.pk for s in page]

    assignee_pks: set[int] = set()
    timeline_pks: set[int] = set()
    if page_pks:
        assignee_pks = set(
            FormSubmission.objects.filter(pk__in=page_pks)
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
                submission_id__in=page_pks,
                created_by=user,
                kind__in=kinds,
            ).values_list("submission_id", flat=True)
        )

    if page:
        qs_ann = _annotate_has_unread_thread(
            FormSubmission.objects.filter(pk__in=page_pks).select_related(
                "form", "form__entity", "current_step", "submitted_by"
            ),
            user,
        )
        by_pk = {s.pk: s for s in qs_ann}
        page = [by_pk[s.pk] for s in page if s.pk in by_pk]

    items = []
    for submission in page:
        row = serialize_inbox_item(request, submission)
        row["role_labels"] = _search_role_labels(
            user,
            submission,
            assignee_pks=assignee_pks,
            timeline_pks=timeline_pks,
        )
        items.append(row)

    form_options = []
    form_ids = (
        FormSubmission.objects.filter(q_rel, form__deleted_at__isnull=True)
        .values_list("form_id", flat=True)
        .distinct()[:200]
    )
    if form_ids:
        forms = forms_queryset_for_user(user, request=request).filter(pk__in=form_ids)
        form_options = [
            {"id": f.pk, "title": f.title, "slug": f.slug, "entity_name": f.entity.name}
            for f in forms.order_by("title")
        ]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "relation": relation,
        "workflow_state": wf if wf else "",
        "form_id": int(form_raw) if form_raw.isdigit() else None,
        "q": search_q,
        "sort": sort_key,
        "form_options": form_options,
        "items": items,
    }
