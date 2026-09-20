"""
Visual workflow builder (studio → form → Workflow).

The page renders a vertical path (applicant submits → step → step → end) with "+" insert
points and a side panel for the selected step. Every mutation below returns the full
builder state so the client simply re-renders from the server's answer.
"""

from __future__ import annotations

import json

from .opaque_ids import encode as oid_encode
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from .entity_access import entity_users_for_entity
from .entity_permissions import MANAGE_FORMS_WRITE
from .manage_capabilities import studio_capability_required
from .models import WorkflowStep
from .slug_utils import unique_workflow_step_slug

LABEL_MAX = WorkflowStep._meta.get_field("label").max_length
DESCRIPTION_MAX = WorkflowStep._meta.get_field("description").max_length


def _user_text(u) -> str:
    text = u.get_username()
    full = u.get_full_name()
    if full:
        text += f" — {full}"
    return text


def builder_state(form_instance) -> dict:
    """Serializable snapshot of the form's workflow for the builder."""
    steps = (
        form_instance.workflow_steps.order_by("order", "id")
        .prefetch_related("assigned_users")
        .annotate(submissions_count=Count("submissions_here", distinct=True))
    )
    return {
        "form_id": form_instance.pk,
        "is_published": bool(form_instance.is_published),
        "steps": [
            {
                "id": s.pk,
                "delete_url": reverse("manage:workflow_builder_delete", kwargs={"pk": form_instance.pk, "step_id": s.pk}),
                "label": s.label,
                "description": s.description,
                "slug": s.slug,
                "assignees": [{"id": u.pk, "text": _user_text(u)} for u in s.assigned_users.all()],
                "submissions_count": s.submissions_count,
            }
            for s in steps
        ],
    }


def builder_i18n() -> dict:
    """Strings the client-side renderer needs (translated server-side)."""
    return {
        "start": _("Applicant submits the form"),
        "end": _("End"),
        "new_step": _("New step"),
        "no_assignee": _("No assignee"),
        "unsaved": _("Not saved yet"),
        "insert_here": _("Insert a step here"),
        "assignee_count": _("%(count)s assignee(s)"),
        "check_ok": _("The path is complete. Every step has someone responsible."),
        "check_no_steps": _("Add at least one step. Forms without workflow steps cannot be published."),
        "check_no_assignee": _("Step “%(label)s” has no assignee, so nobody receives submissions there."),
        "check_unsaved": _("A new step is not saved yet."),
        "check_duplicate": _("Step name “%(label)s” is used more than once."),
        "err_label_required": _("Enter a step name."),
        "err_network": _("Could not reach the server. Check your connection and try again."),
        "confirm_discard": _("Discard unsaved changes to this step?"),
        "confirm_delete": _("Remove this step?"),
        "saved": _("Saved."),
        "deleted": _("Step removed."),
        "submissions_here": _("%(count)s submission(s) are currently on this step. Move them before removing it."),
    }


def _json_body(request) -> dict | None:
    try:
        payload = json.loads(request.body.decode() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _clean_assignee_ids(raw, form_instance) -> list[int] | None:
    """Return valid member ids, or None when the list contains a non-member."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        return None
    ids: list[int] = []
    for v in raw:
        try:
            ids.append(int(v))
        except (TypeError, ValueError):
            return None
    if not ids:
        return []
    if form_instance.entity_id:
        allowed = set(
            entity_users_for_entity(form_instance.entity_id).filter(pk__in=ids).values_list("pk", flat=True)
        )
    else:
        allowed = set(
            get_user_model().objects.filter(is_active=True, pk__in=ids).values_list("pk", flat=True)
        )
    if set(ids) - allowed:
        return None
    return list(dict.fromkeys(ids))


def _reindex(form_instance) -> None:
    for index, sid in enumerate(
        form_instance.workflow_steps.order_by("order", "id").values_list("pk", flat=True)
    ):
        WorkflowStep.objects.filter(pk=sid).update(order=index)


@studio_capability_required(MANAGE_FORMS_WRITE)
def workflow_builder_page(request, pk):
    from .manage_views import _form_for_manage

    form_instance = _form_for_manage(request, pk)
    search_url = reverse("manage:user_search") + f"?form={oid_encode(form_instance.pk)}&scope=entity"
    return render(
        request,
        "magicforms/manage/workflow_list.html",
        {
            "form_obj": form_instance,
            "builder_state": builder_state(form_instance),
            "builder_i18n": builder_i18n(),
            "assignee_search_url": search_url,
        },
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_GET
def workflow_builder_state(request, pk):
    from .manage_views import _form_for_manage

    form_instance = _form_for_manage(request, pk)
    return JsonResponse({"ok": True, "state": builder_state(form_instance)})


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def workflow_builder_save(request, pk):
    """
    Create or update one step.

    Body: ``{"id": <step id or null>, "label", "description", "assignee_ids": [...],
    "insert_after": <step id> | "start" | null}``. ``insert_after`` applies to new steps only;
    ``"start"`` places the step first and ``null`` appends it.
    """
    from .manage_views import _form_for_manage, _maybe_unpublish

    form_instance = _form_for_manage(request, pk)
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": _("Invalid request.")}, status=400)

    label = str(payload.get("label") or "").strip()
    description = str(payload.get("description") or "").strip()
    if not label:
        return JsonResponse({"ok": False, "error": _("Enter a step name."), "field": "label"}, status=400)
    if len(label) > LABEL_MAX:
        return JsonResponse(
            {"ok": False, "error": _("Step name is too long."), "field": "label"}, status=400
        )
    if len(description) > DESCRIPTION_MAX:
        return JsonResponse(
            {"ok": False, "error": _("Description is too long."), "field": "description"}, status=400
        )
    assignee_ids = _clean_assignee_ids(payload.get("assignee_ids"), form_instance)
    if assignee_ids is None:
        return JsonResponse(
            {
                "ok": False,
                "error": _("Choose assignees from this organization's members only."),
                "field": "assignees",
            },
            status=400,
        )

    step_id = payload.get("id")
    with transaction.atomic():
        if step_id:
            step = get_object_or_404(WorkflowStep, pk=step_id, form=form_instance)
            step.label = label
            step.description = description
            step.save(update_fields=["label", "description"])
        else:
            insert_after = payload.get("insert_after")
            ordered = list(form_instance.workflow_steps.order_by("order", "id"))
            if insert_after == "start":
                position = 0
            elif insert_after in (None, ""):
                position = len(ordered)
            else:
                try:
                    anchor = int(insert_after)
                except (TypeError, ValueError):
                    return JsonResponse({"ok": False, "error": _("Invalid request.")}, status=400)
                idx = next((i for i, s in enumerate(ordered) if s.pk == anchor), None)
                if idx is None:
                    return JsonResponse({"ok": False, "error": _("Invalid request.")}, status=400)
                position = idx + 1
            # Make room: shift everything at/after the position down by one.
            for s in ordered[position:]:
                WorkflowStep.objects.filter(pk=s.pk).update(order=s.order + 1 + len(ordered))
            step = WorkflowStep.objects.create(
                form=form_instance,
                order=position,
                label=label,
                description=description,
                slug=unique_workflow_step_slug(label, form_instance),
            )
            _reindex(form_instance)
        step.assigned_users.set(assignee_ids)

    _maybe_unpublish(form_instance)
    return JsonResponse({"ok": True, "step_id": step.pk, "state": builder_state(form_instance)})


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def workflow_builder_delete(request, pk, step_id):
    from .manage_views import _form_for_manage, _maybe_unpublish

    form_instance = _form_for_manage(request, pk)
    step = get_object_or_404(WorkflowStep, pk=step_id, form=form_instance)
    try:
        with transaction.atomic():
            step.delete()
            _reindex(form_instance)
    except ProtectedError:
        return JsonResponse(
            {
                "ok": False,
                "error": _(
                    "Cannot delete this step while submissions reference it. Move submissions to another step first."
                ),
                "state": builder_state(form_instance),
            },
            status=409,
        )
    unpublished = _maybe_unpublish(form_instance)
    return JsonResponse(
        {"ok": True, "unpublished": unpublished, "state": builder_state(form_instance)}
    )
