"""Shared workflow approve/reject logic (studio + mobile API)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F

from magicforms.models import EntityMembership, FormSubmission, FormSubmitRoutePick, SubmissionEvent
from magicforms.workflow_access import (
    delegate_action_suffix,
    dynamic_delegate_action_suffix,
    form_supports_workflow_decisions,
    user_may_act_on_submission_workflow,
)


def _submit_route_role_candidates(form_instance, role: str):
    from magicforms.entity_access import entity_users_for_entity

    return entity_users_for_entity(form_instance.entity_id).filter(profile__job_title__icontains=role)


def _record_submit_route_pick(form_instance, target, *, was_unclaimed: bool) -> None:
    """
    A human manually routing an unclaimed submission for a role-bound form, to someone who
    actually holds that role, adds one to that person's pick count for this form. The most
    frequently picked current role-holder becomes the auto-route suggestion (see
    ``apply_submit_route_role``). Routing at any later hop, or to someone who doesn't hold the
    role, doesn't count.
    """
    role = (form_instance.submit_route_role or "").strip()
    if not was_unclaimed or not role:
        return
    if not _submit_route_role_candidates(form_instance, role).filter(pk=target.pk).exists():
        return
    pick, _created = FormSubmitRoutePick.objects.get_or_create(form=form_instance, user=target)
    FormSubmitRoutePick.objects.filter(pk=pick.pk).update(times_picked=F("times_picked") + 1)


def apply_submit_route_role(submission: FormSubmission) -> None:
    """
    Dynamic routing only. Called right after a submission is created: if the form defines a
    submit-stage role, auto-claim the (still unclaimed) submission on behalf of whoever holds
    that role, so it doesn't sit open when the answer is obvious.

    Picks, in order: the current role-holder most frequently routed to on this form (only when
    they're the clear, unique leader), otherwise the sole current holder of the role. If nobody
    holds it, or more than one person does with no clear favorite, the submission is left open
    for any organization member to claim, same as a dynamic-routing form with no role set.
    """
    form_instance = submission.form
    role = (form_instance.submit_route_role or "").strip()
    if not form_instance.uses_dynamic_routing or not role:
        return

    candidates = _submit_route_role_candidates(form_instance, role)
    candidate_ids = list(candidates.values_list("pk", flat=True))
    if not candidate_ids:
        return

    top_picks = list(
        FormSubmitRoutePick.objects.filter(form=form_instance, user_id__in=candidate_ids)
        .select_related("user")
        .order_by("-times_picked")[:2]
    )
    target = None
    if top_picks and (len(top_picks) == 1 or top_picks[0].times_picked > top_picks[1].times_picked):
        target = top_picks[0].user
    elif len(candidate_ids) == 1:
        target = candidates.first()

    if target is None:
        return

    submission.current_holder = target
    submission.save(update_fields=["current_holder"])
    target_label = target.get_full_name() or target.get_username()
    SubmissionEvent.objects.create(
        submission=submission,
        kind=SubmissionEvent.Kind.ROUTED,
        message=f"Automatically routed to {target_label} ({role}).",
    )


def perform_workflow_decision(
    *,
    user,
    submission: FormSubmission,
    decision: str,
    comment: str = "",
    workflow_action_anchor: int | None = None,
) -> tuple[bool, str | None, dict | None]:
    """
    Approve or reject a submission at its current workflow step.

    Returns ``(ok, error_message, result)`` where ``result`` on success may include
    ``outcome`` (``rejected`` | ``completed`` | ``advanced``) and ``step_label``.
    """
    from magicforms.supplementary import ensure_related_invitations

    form_instance = submission.form
    decision = (decision or "").strip().lower()
    if decision not in ("approve", "reject"):
        return False, "Unrecognized workflow action.", None

    if not form_instance.workflow_steps.exists():
        return False, "This form has no workflow steps.", None
    if not form_supports_workflow_decisions(form_instance):
        return False, "Dynamic routing is being set up for this form; workflow actions aren't available yet.", None

    comment = (comment or "").strip()[:800]
    if decision == "reject" and not comment:
        return False, "Enter a reason for rejection before submitting.", None

    workflow_block_error: str | None = None
    approve_outcome: str | tuple[str, str] | None = None

    with transaction.atomic():
        fresh = (
            FormSubmission.objects.select_related("current_step")
            .prefetch_related("current_step__assigned_users")
            .select_for_update()
            .get(pk=submission.pk, form=form_instance)
        )
        if fresh.workflow_state != FormSubmission.WorkflowState.IN_PROGRESS:
            workflow_block_error = "This submission is not awaiting approval."
        elif not fresh.current_step_id:
            workflow_block_error = "Assign a workflow step before using approve or reject."
        elif not user_may_act_on_submission_workflow(user, fresh):
            workflow_block_error = (
                "You are not an assignee on this step and do not have an active delegation to act here."
            )
        elif workflow_action_anchor is not None and workflow_action_anchor != int(
            fresh.current_step_id
        ):
            workflow_block_error = (
                "This submission was already updated—refresh and try again."
            )
        else:
            delegate_suffix = delegate_action_suffix(user, fresh)

            def event_message(base: str) -> str:
                combined = base + delegate_suffix
                if not comment:
                    return combined[:1000]
                suffix = f"\n\nComment: {comment}"
                if len(combined) + len(suffix) <= 1000:
                    return combined + suffix
                room = max(0, 1000 - len(combined) - len("\n\nComment: "))
                return combined + "\n\nComment: " + comment[:room]

            if decision == "reject":
                fresh.workflow_state = FormSubmission.WorkflowState.REJECTED
                fresh.save(update_fields=["workflow_state", "updated_at"])
                SubmissionEvent.objects.create(
                    submission=fresh,
                    kind=SubmissionEvent.Kind.WORKFLOW_REJECTED,
                    step=fresh.current_step,
                    message=event_message("Workflow rejected; stopped at this step."),
                    created_by=user,
                )
            else:
                ensure_related_invitations(fresh)
                next_step = form_instance.next_workflow_step_after(fresh.current_step)
                if next_step is None:
                    fresh.current_step = None
                    fresh.workflow_state = FormSubmission.WorkflowState.COMPLETED
                    fresh.save(
                        update_fields=["current_step", "workflow_state", "updated_at"],
                    )
                    SubmissionEvent.objects.create(
                        submission=fresh,
                        kind=SubmissionEvent.Kind.WORKFLOW_COMPLETED,
                        step=None,
                        message=event_message("All workflow steps approved; submission complete."),
                        created_by=user,
                    )
                    approve_outcome = "completed"
                else:
                    fresh.current_step = next_step
                    fresh.save(update_fields=["current_step", "updated_at"])
                    SubmissionEvent.objects.create(
                        submission=fresh,
                        kind=SubmissionEvent.Kind.STEP_APPROVED,
                        step=next_step,
                        message=event_message(f'Approved; advanced to "{next_step.label}".'),
                        created_by=user,
                    )
                    approve_outcome = ("advanced", str(next_step.label))
                ensure_related_invitations(fresh)

            submission.refresh_from_db()

        if workflow_block_error:
            return False, workflow_block_error, None

        if decision == "reject":
            result = {"outcome": "rejected", "message": "Submission rejected; workflow stopped here."}
        elif approve_outcome == "completed":
            result = {"outcome": "completed", "message": "Approved — workflow is complete."}
        elif isinstance(approve_outcome, tuple):
            result = {
                "outcome": "advanced",
                "step_label": approve_outcome[1],
                "message": f'Approved — now at "{approve_outcome[1]}".',
            }
        elif decision == "approve":
            return False, "Approval did not complete. Refresh and try again.", None
        else:
            result = {"outcome": decision, "message": "Done."}

        from magicforms.notification_emails import queue_after_submission_event

        latest_event = (
            SubmissionEvent.objects.filter(submission_id=submission.pk).order_by("-pk").first()
        )
        if latest_event is not None:
            queue_after_submission_event(
                submission,
                latest_event,
                workflow_decision=decision,
                workflow_decision_comment=comment,
                staff_user=user,
            )

        return True, None, result


def perform_dynamic_route_decision(
    *,
    user,
    submission: FormSubmission,
    action: str,
    target_user_id: int | None = None,
    stage_label: str = "",
    comment: str = "",
) -> tuple[bool, str | None, dict | None]:
    """
    Dynamic routing: route the submission to exactly one chosen person, mark it complete, or
    reject it (always back to the original submitter; nothing further to route).

    Returns ``(ok, error_message, result)`` where ``result`` on success may include ``outcome``
    (``routed`` | ``completed`` | ``rejected``) and, for ``routed``, ``target_label``.
    """
    from magicforms.supplementary import ensure_related_invitations

    form_instance = submission.form
    action = (action or "").strip().lower()
    if action not in ("route", "complete", "reject"):
        return False, "Unrecognized workflow action.", None
    if not form_instance.uses_dynamic_routing:
        return False, "This form uses fixed workflow steps, not dynamic routing.", None

    comment = (comment or "").strip()[:800]
    stage_label = (stage_label or "").strip()[:255]
    if action == "reject" and not comment:
        return False, "Enter a reason for rejection before submitting.", None
    if action == "route" and not target_user_id:
        return False, "Choose who this goes to next.", None

    workflow_block_error: str | None = None
    outcome: dict | None = None

    with transaction.atomic():
        fresh = (
            FormSubmission.objects.select_related("form", "current_holder")
            .select_for_update()
            .get(pk=submission.pk, form=form_instance)
        )
        was_unclaimed = fresh.current_holder_id is None
        if fresh.workflow_state != FormSubmission.WorkflowState.IN_PROGRESS:
            workflow_block_error = "This submission is not awaiting approval."
        elif not user_may_act_on_submission_workflow(user, fresh):
            workflow_block_error = (
                "You do not currently hold this submission and do not have an active "
                "delegation to act on it."
            )
        else:
            delegate_suffix = dynamic_delegate_action_suffix(user, fresh)

            def event_message(base: str) -> str:
                combined = base + delegate_suffix
                if not comment:
                    return combined[:1000]
                suffix = f"\n\nNote: {comment}"
                if len(combined) + len(suffix) <= 1000:
                    return combined + suffix
                room = max(0, 1000 - len(combined) - len("\n\nNote: "))
                return combined + "\n\nNote: " + comment[:room]

            if action == "route":
                User = get_user_model()
                target = User.objects.filter(pk=target_user_id, is_active=True).first()
                is_org_member = bool(target) and EntityMembership.objects.filter(
                    user_id=target.pk, entity_id=form_instance.entity_id
                ).exists()
                if target is None:
                    workflow_block_error = "That person could not be found. Refresh and try again."
                elif target.pk == user.pk:
                    workflow_block_error = "Choose someone other than yourself."
                elif not is_org_member and not target.is_superuser:
                    workflow_block_error = "Choose someone from this form's organization."
                else:
                    ensure_related_invitations(fresh)
                    fresh.current_holder = target
                    fresh.current_stage_label = stage_label
                    fresh.save(
                        update_fields=["current_holder", "current_stage_label", "updated_at"]
                    )
                    target_label = target.get_full_name() or target.get_username()
                    base_msg = (
                        f"Routed to {target_label} ({stage_label})."
                        if stage_label
                        else f"Routed to {target_label}."
                    )
                    SubmissionEvent.objects.create(
                        submission=fresh,
                        kind=SubmissionEvent.Kind.ROUTED,
                        message=event_message(base_msg),
                        created_by=user,
                    )
                    _record_submit_route_pick(form_instance, target, was_unclaimed=was_unclaimed)
                    outcome = {
                        "outcome": "routed",
                        "target_label": target_label,
                        "message": f"Routed to {target_label}.",
                    }
            elif action == "complete":
                ensure_related_invitations(fresh)
                fresh.current_holder = None
                fresh.current_stage_label = ""
                fresh.workflow_state = FormSubmission.WorkflowState.COMPLETED
                fresh.save(
                    update_fields=[
                        "current_holder",
                        "current_stage_label",
                        "workflow_state",
                        "updated_at",
                    ]
                )
                SubmissionEvent.objects.create(
                    submission=fresh,
                    kind=SubmissionEvent.Kind.WORKFLOW_COMPLETED,
                    message=event_message("Marked complete."),
                    created_by=user,
                )
                outcome = {"outcome": "completed", "message": "Marked complete."}
            else:  # reject
                fresh.current_holder = None
                fresh.workflow_state = FormSubmission.WorkflowState.REJECTED
                fresh.save(update_fields=["current_holder", "workflow_state", "updated_at"])
                SubmissionEvent.objects.create(
                    submission=fresh,
                    kind=SubmissionEvent.Kind.WORKFLOW_REJECTED,
                    message=event_message("Rejected; returned to the original submitter."),
                    created_by=user,
                )
                outcome = {
                    "outcome": "rejected",
                    "message": "Rejected; returned to the original submitter.",
                }

            submission.refresh_from_db()

        if workflow_block_error:
            return False, workflow_block_error, None
        if outcome is None:
            return False, "Action did not complete. Refresh and try again.", None

        from magicforms.notification_emails import queue_after_submission_event

        latest_event = (
            SubmissionEvent.objects.filter(submission_id=submission.pk).order_by("-pk").first()
        )
        if latest_event is not None:
            queue_after_submission_event(
                submission,
                latest_event,
                workflow_decision=action,
                workflow_decision_comment=comment,
                staff_user=user,
            )

        return True, None, outcome
