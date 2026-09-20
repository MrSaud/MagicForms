"""Data helpers for mobile home, published forms, and inbox."""

from __future__ import annotations

from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateformat import format as date_format

from magicforms.entity_access import effective_entity_ids, published_forms_for_public_home
from magicforms.mobile_auth import user_may_use_mobile_api
from magicforms.models import FormSubmission, StaffInboxSubmissionDetailView
from magicforms.models import FieldType
from magicforms.outbound.file_urls import absolute_outbound_file_url
from magicforms.print_merge import _display_value
from magicforms.subdomain import apex_site_url, portal_absolute_uri, studio_manage_url
from magicforms.supplementary import related_pending_count_for_user
from magicforms.workflow_access import (
    inbox_list_queryset,
    inbox_open_count_for_user,
    inbox_submissions_filter_q,
    submission_in_portal_search_scope,
    user_may_act_on_submission_workflow,
)


def _mobile_request_user(request: HttpRequest):
    return getattr(request, "mobile_user", None)


def _iso_dt(dt) -> str:
    if not dt:
        return ""
    return timezone.localtime(dt).isoformat()


def _dt_label(dt) -> str:
    if not dt:
        return ""
    return date_format(timezone.localtime(dt), "M j, Y, P")


def mobile_home_summary(request: HttpRequest) -> dict:
    from magicforms.entity_branding import mobile_banner_branding

    user = _mobile_request_user(request)
    inbox_count = inbox_open_count_for_user(user, request)
    applicant_pending = related_pending_count_for_user(user)
    base = apex_site_url(request).rstrip("/")
    branding = mobile_banner_branding(user, request)
    return {
        "inbox_count": inbox_count,
        "applicant_pending_count": applicant_pending,
        "is_staff": bool(getattr(user, "is_staff", False)),
        "is_superuser": bool(getattr(user, "is_superuser", False)),
        "banner_logo_url": branding.get("banner_logo_url") or "",
        "banner_entity_name": branding.get("banner_entity_name") or "",
        "menu_links": {
            "studio_home": studio_manage_url(request, "/manage/"),
            "inbox": studio_manage_url(request, "/manage/inbox/"),
            "submission_search": studio_manage_url(request, "/manage/submissions/search/"),
            "my_signatures": f"{base}/account/signatures/",
            "public_site": base + "/",
            "help": studio_manage_url(request, "/manage/help/"),
        },
    }


def _form_public_url(request: HttpRequest, form) -> str:
    query = {"share": str(form.public_share_key)} if form.public_share_key else None
    return portal_absolute_uri(
        request,
        "magicforms:form_public",
        entity=form.entity,
        slug=form.slug,
        query=query,
    )


def serialize_published_form(request: HttpRequest, form) -> dict:
    category = form.category
    deadline = form.submission_deadline
    intro_enabled = bool(form.intro_page_enabled)
    public_url = _form_public_url(request, form)
    return {
        "id": form.pk,
        "title": form.title,
        "slug": form.slug,
        "description": (form.description or "")[:500],
        "entity": {
            "id": form.entity_id,
            "slug": form.entity.slug,
            "name": form.entity.name,
        },
        "category": (
            {"slug": category.slug, "name": category.name} if category else None
        ),
        "submission_deadline": deadline.isoformat() if deadline else None,
        "submission_deadline_label": date_format(deadline, "M j, Y") if deadline else "",
        "is_for_public": form.is_for_public,
        "layout_direction": form.public_dir(),
        "public_url": public_url,
        "intro_page_enabled": intro_enabled,
        "intro_page_url": public_url if intro_enabled else "",
    }


def user_may_access_published_form(user, form, request=None) -> bool:
    """Whether ``form`` would appear in this user's published forms list."""
    return published_forms_for_public_home(user).filter(pk=form.pk).exists()


def published_forms_payload(request: HttpRequest) -> list[dict]:
    user = _mobile_request_user(request)
    if not user_may_use_mobile_api(user):
        return []
    qs = published_forms_for_public_home(user)
    return [serialize_published_form(request, f) for f in qs[:200]]


def _inbox_queryset(request: HttpRequest):
    from magicforms.manage_views import _annotate_has_unread_thread

    user = _mobile_request_user(request)
    qs = inbox_list_queryset(user, request).select_related(
        "form", "form__entity", "current_step", "submitted_by"
    )
    return _annotate_has_unread_thread(qs, user).order_by("-submitted_at")


def _submission_workflow_flags(user, submission) -> dict:
    form = submission.form
    has_steps = form.workflow_steps.exists()
    can_act = (
        has_steps
        and submission.workflow_state == FormSubmission.WorkflowState.IN_PROGRESS
        and submission.current_step_id
        and user_may_act_on_submission_workflow(user, submission)
    )
    acting_as_delegate = False
    if can_act and submission.current_step_id:
        assignee_pks = set(submission.current_step.assigned_users.values_list("pk", flat=True))
        acting_as_delegate = user.pk not in assignee_pks
    return {
        "can_act": can_act,
        "acting_as_delegate": acting_as_delegate,
        "has_workflow_steps": has_steps,
    }


def serialize_inbox_item(request: HttpRequest, submission) -> dict:
    user = _mobile_request_user(request)
    form = submission.form
    step = submission.current_step
    submitted_by = submission.submitted_by
    submitter = ""
    if submitted_by:
        submitter = submitted_by.get_full_name() or submitted_by.username
    elif submission.submitter_email:
        submitter = submission.submitter_email
    flags = _submission_workflow_flags(user, submission)
    return {
        "id": submission.pk,
        "reference_token": submission.reference_token or "",
        "workflow_state": submission.workflow_state,
        "workflow_state_label": submission.get_workflow_state_display(),
        "form": {
            "id": form.pk,
            "title": form.title,
            "slug": form.slug,
            "entity_slug": form.entity.slug,
            "entity_name": form.entity.name,
        },
        "submitter": submitter,
        "submitted_at": _iso_dt(submission.submitted_at),
        "submitted_at_label": _dt_label(submission.submitted_at),
        "current_step_id": submission.current_step_id,
        "current_step_label": (step.label if step else "") or "",
        "has_unread_thread": bool(getattr(submission, "has_unread_thread", False)),
        "can_act": flags["can_act"],
        "manage_url": studio_manage_url(
            request,
            f"/manage/forms/{form.pk}/submissions/{submission.pk}/",
        ),
    }


def inbox_list_payload(request: HttpRequest, *, limit: int = 50, offset: int = 0) -> dict:
    qs = _inbox_queryset(request)
    total = qs.count()
    page = list(qs[offset : offset + limit])
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [serialize_inbox_item(request, s) for s in page],
    }


def _get_submission_for_mobile(request: HttpRequest, submission_id: int):
    user = _mobile_request_user(request)
    submission = get_object_or_404(
        FormSubmission.objects.select_related(
            "form",
            "form__entity",
            "current_step",
            "submitted_by",
        ).prefetch_related(
            "current_step__assigned_users",
            "values__field",
            "events__step",
            "events__created_by",
            "document_attachments",
        ),
        pk=submission_id,
        form__deleted_at__isnull=True,
    )
    if not _user_may_view_submission_mobile(user, submission, request):
        raise Http404
    return submission


def _user_may_view_submission_mobile(user, submission, request) -> bool:
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    return submission_in_portal_search_scope(user, submission, request)


def record_inbox_detail_viewed(user, submission) -> None:
    StaffInboxSubmissionDetailView.objects.get_or_create(
        user=user,
        submission=submission,
    )


def _serialize_submission_value(request: HttpRequest, sv) -> dict:
    field = sv.field
    payload = {
        "value_id": sv.pk,
        "field_name": field.name,
        "field_label": field.label,
        "field_type": field.field_type,
        "display_value": _display_value(field, sv),
        "required": field.required,
        "attachment": None,
    }
    if field.field_type == FieldType.FILE and sv.attachment:
        payload["attachment"] = {
            "filename": (sv.value or "").strip() or sv.attachment.name.split("/")[-1],
            "download_url": absolute_outbound_file_url(sv.pk, request),
            "api_path": f"/api/v1/inbox/{sv.submission_id}/values/{sv.pk}/attachment/",
        }
    return payload


def inbox_detail_payload(request: HttpRequest, submission_id: int) -> dict:
    user = _mobile_request_user(request)
    submission = _get_submission_for_mobile(request, submission_id)
    record_inbox_detail_viewed(user, submission)
    from magicforms.api.mobile_thread import thread_messages_payload, touch_thread_last_read

    touch_thread_last_read(user, submission)
    from magicforms.api.mobile_documents import documents_block_payload

    form = submission.form
    step = submission.current_step
    submitted_by = submission.submitted_by
    submitter = ""
    if submitted_by:
        submitter = submitted_by.get_full_name() or submitted_by.username
    elif submission.submitter_email:
        submitter = submission.submitter_email

    flags = _submission_workflow_flags(user, submission)
    values = sorted(submission.values.all(), key=lambda v: (v.field.order, v.field_id))
    events = list(submission.events.all())

    return {
        "submission": {
            "id": submission.pk,
            "reference_token": submission.reference_token or "",
            "workflow_state": submission.workflow_state,
            "workflow_state_label": submission.get_workflow_state_display(),
            "submitted_at": _iso_dt(submission.submitted_at),
            "submitted_at_label": _dt_label(submission.submitted_at),
            "updated_at": _iso_dt(submission.updated_at),
            "updated_at_label": _dt_label(submission.updated_at),
            "submitter": submitter,
            "submitter_email": submission.submitter_email or "",
            "current_step_id": submission.current_step_id,
            "current_step_label": (step.label if step else "") or "",
            "can_act": flags["can_act"],
            "acting_as_delegate": flags["acting_as_delegate"],
            "reject_comment_required": True,
            "form": {
                "id": form.pk,
                "title": form.title,
                "slug": form.slug,
                "entity_slug": form.entity.slug,
                "entity_name": form.entity.name,
            },
            "manage_url": studio_manage_url(
                request,
                f"/manage/forms/{form.pk}/submissions/{submission.pk}/",
            ),
        },
        "values": [_serialize_submission_value(request, sv) for sv in values],
        "documents": documents_block_payload(request, submission),
        "thread": thread_messages_payload(request, submission_id),
        "events": [
            {
                "id": ev.pk,
                "kind": ev.kind,
                "kind_label": ev.get_kind_display(),
                "message": ev.message or "",
                "created_at": _iso_dt(ev.created_at),
                "created_at_label": _dt_label(ev.created_at),
                "step_label": (ev.step.label if ev.step_id and ev.step else "") or "",
                "author": (
                    (ev.created_by.get_full_name() or ev.created_by.username)
                    if ev.created_by_id
                    else ""
                ),
            }
            for ev in events
        ],
    }
