"""
Workflow assignee access: direct assignees and active delegates (see ``WorkflowDelegation``).
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone


def form_supports_workflow_decisions(form) -> bool:
    """
    True when ``form`` may use approve/reject at all right now.

    Fixed-step forms (the only mode implemented today) always do. Forms an admin has switched to
    dynamic routing pause approve/reject until that engine ships, rather than run the old fixed-step
    logic against steps that are no longer wired as a pipeline.
    """
    return form.routing_mode == form.RoutingMode.FIXED_STEPS


def delegator_ids_where_user_is_active_delegate(user, entity_id: int | None) -> list[int]:
    """User IDs who currently delegate their inbox / step actions to ``user`` within ``entity_id``."""
    from .models import WorkflowDelegation

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return []
    if entity_id is None:
        return []
    today = timezone.localdate()
    qs = WorkflowDelegation.objects.filter(
        delegate=user,
        is_active=True,
        entity_id=entity_id,
    )
    qs = qs.filter(Q(valid_from__isnull=True) | Q(valid_from__lte=today))
    qs = qs.filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
    return list(qs.values_list("delegator_id", flat=True).distinct())


def user_may_act_on_submission_workflow(user, submission) -> bool:
    """
    True if ``user`` may approve/reject (or, in dynamic routing, route/complete/reject) this
    submission right now: a direct assignee on the current step, or the current holder, or an
    active delegate for either.
    """
    from .models import EntityMembership, Form, FormSubmission

    if submission.workflow_state != FormSubmission.WorkflowState.IN_PROGRESS:
        return False

    if submission.form.routing_mode == Form.RoutingMode.DYNAMIC:
        if submission.current_holder_id:
            if user.pk == submission.current_holder_id:
                return True
            delegator_ids = set(
                delegator_ids_where_user_is_active_delegate(user, submission.form.entity_id)
            )
            return submission.current_holder_id in delegator_ids
        # Unclaimed: any active member of the submission's organization may take the first hop.
        return bool(getattr(user, "is_superuser", False)) or EntityMembership.objects.filter(
            user=user, entity_id=submission.form.entity_id
        ).exists()

    if not submission.current_step_id:
        return False
    step = submission.current_step
    assignee_ids = set(step.assigned_users.values_list("pk", flat=True))
    if not assignee_ids:
        return False
    if user.pk in assignee_ids:
        return True
    entity_id = submission.form.entity_id
    delegator_ids = set(delegator_ids_where_user_is_active_delegate(user, entity_id))
    return bool(assignee_ids & delegator_ids)


def dynamic_delegate_action_suffix(user, submission) -> str:
    """Short audit suffix when the actor is acting as a delegate for the current holder (dynamic routing)."""
    from django.contrib.auth import get_user_model

    holder_id = submission.current_holder_id
    if not holder_id or user.pk == holder_id:
        return ""
    entity_id = submission.form.entity_id
    delegator_ids = set(delegator_ids_where_user_is_active_delegate(user, entity_id))
    if holder_id not in delegator_ids:
        return ""
    User = get_user_model()
    holder = User.objects.filter(pk=holder_id).first()
    if holder is None:
        return " [delegate]"
    return f" [delegate for: {holder.get_username()}]"


def inbox_submissions_filter_q(user, entity_ids: list[int] | None):
    """
    ``Q`` for submissions visible in the staff inbox (assignee or delegate).
    ``entity_ids`` is ``None`` for superusers (no entity filter); otherwise restrict to those entities.
    Delegations apply only to submissions in the same entity as the delegation row.
    Dynamic-routing submissions are matched by ``current_holder`` instead of a step's assignees.
    """
    from .models import Form, WorkflowDelegation

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Q(pk__in=[])
    today = timezone.localdate()
    del_qs = WorkflowDelegation.objects.filter(delegate=user, is_active=True)
    del_qs = del_qs.filter(Q(valid_from__isnull=True) | Q(valid_from__lte=today))
    del_qs = del_qs.filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
    if entity_ids is not None:
        del_qs = del_qs.filter(entity_id__in=entity_ids)

    q_direct = Q(current_step__assigned_users=user) | Q(
        form__routing_mode=Form.RoutingMode.DYNAMIC, current_holder=user
    )
    q_delegate = Q()
    for eid, did in del_qs.values_list("entity_id", "delegator_id").distinct():
        q_delegate |= Q(form__entity_id=eid, current_step__assigned_users=did)
        q_delegate |= Q(
            form__entity_id=eid, form__routing_mode=Form.RoutingMode.DYNAMIC, current_holder_id=did
        )
    # Freshly submitted dynamic-routing items have no holder yet; any member of the organization
    # may take the first routing action, so surface them here too (mirrors the permission bootstrap
    # rule in ``user_may_act_on_submission_workflow``).
    q_unclaimed = Q(form__routing_mode=Form.RoutingMode.DYNAMIC, current_holder__isnull=True)
    if entity_ids is not None:
        q_unclaimed &= Q(form__entity_id__in=entity_ids)

    q = q_direct | q_delegate | q_unclaimed
    if entity_ids is not None:
        q &= Q(form__entity_id__in=entity_ids)
    return q


def applicant_submissions_filter_q(user) -> Q:
    """
    Submissions where ``user`` is the applicant: signed in as ``submitted_by``,
    or (when their account has an email) ``submitter_email`` matches case-insensitively.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Q(pk__in=[])
    q = Q(submitted_by=user)
    email = (getattr(user, "email", None) or "").strip()
    if email:
        q |= Q(submitter_email__iexact=email)
    return q


def submission_in_portal_search_scope(user, submission, request) -> bool:
    """
    True when ``submission`` would appear on submission search with relation "any"
    (applicant, inbox assignee/delegate, timeline events authored by the user, or thread messages).
    Used to gate manage submission views for non-staff portal members.
    """
    from .entity_access import effective_entity_ids
    from .models import FormSubmission

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    eids = effective_entity_ids(user, request)
    q_applicant = applicant_submissions_filter_q(user)
    q_assignee = inbox_submissions_filter_q(user, eids)
    q_timeline = staff_workflow_timeline_filter_q(user, eids)
    q_thread = staff_workflow_thread_filter_q(user, eids)
    q_rel = q_applicant | q_assignee | q_timeline | q_thread
    qs = FormSubmission.objects.filter(
        pk=submission.pk,
        form__deleted_at__isnull=True,
    ).filter(q_rel)
    if eids is not None:
        qs = qs.filter(form__entity_id__in=eids)
    return qs.exists()


def staff_workflow_timeline_filter_q(user, entity_ids) -> Q:
    """
    Submissions where ``user`` appears on the manage timeline (approve/reject/complete,
    notes, forwards, attachments, etc.) — i.e. they participated in the workflow path as staff.
    """
    from .models import SubmissionEvent

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Q(pk__in=[])
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
    ev_qs = SubmissionEvent.objects.filter(created_by=user, kind__in=kinds)
    if entity_ids is not None:
        ev_qs = ev_qs.filter(submission__form__entity_id__in=entity_ids)
    return Q(pk__in=ev_qs.values("submission_id"))


def staff_workflow_thread_filter_q(user, entity_ids) -> Q:
    """
    Submissions where ``user`` posted a manage thread message (keeps access after step moves on).
    """
    from .models import SubmissionThreadMessage

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Q(pk__in=[])
    tm_qs = SubmissionThreadMessage.objects.filter(author=user)
    if entity_ids is not None:
        tm_qs = tm_qs.filter(submission__form__entity_id__in=entity_ids)
    return Q(pk__in=tm_qs.values("submission_id"))


def delegate_action_suffix(user, submission) -> str:
    """Short audit suffix when the actor is acting as a delegate (not a direct assignee)."""
    from django.contrib.auth import get_user_model

    if not submission.current_step_id:
        return ""
    step = submission.current_step
    assignee_ids = set(step.assigned_users.values_list("pk", flat=True))
    if user.pk in assignee_ids:
        return ""
    entity_id = submission.form.entity_id
    delegator_ids = set(delegator_ids_where_user_is_active_delegate(user, entity_id))
    covered = assignee_ids & delegator_ids
    if not covered:
        return ""
    User = get_user_model()
    names = list(
        User.objects.filter(pk__in=covered).order_by("username").values_list("username", flat=True)[:10]
    )
    if not names:
        return " [delegate]"
    return f" [delegate for: {', '.join(names)}]"


def assistant_search_submissions_filter_q(user, entity_ids) -> Q:
    """
    Submissions the inbox assistant may search: same scope as submission search
    with relation ``any`` — applicant, assignee/delegate, timeline, or thread.
    """
    return (
        applicant_submissions_filter_q(user)
        | inbox_submissions_filter_q(user, entity_ids)
        | staff_workflow_timeline_filter_q(user, entity_ids)
        | staff_workflow_thread_filter_q(user, entity_ids)
    )


def assistant_search_list_queryset(user, request=None):
    """All non-deleted submissions tied to ``user`` as applicant or on a workflow path."""
    from .entity_access import effective_entity_ids
    from .models import FormSubmission

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return FormSubmission.objects.none()
    eids = effective_entity_ids(user, request)
    qs = FormSubmission.objects.filter(
        assistant_search_submissions_filter_q(user, eids),
        form__deleted_at__isnull=True,
    ).distinct()
    if eids is not None:
        qs = qs.filter(form__entity_id__in=eids)
    return qs


def inbox_list_queryset(user, request=None):
    """
    Submissions for the staff inbox list: in-progress assignee/delegate items plus
  recently completed submissions the user may still undo (same as studio ``inbox`` view).
    """
    from .entity_access import effective_entity_ids
    from .models import FormSubmission, SubmissionEvent
    from .workflow_undo import UNDO_APPROVE_WINDOW

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return FormSubmission.objects.none()
    eids = effective_entity_ids(user, request)
    base_inbox_qs = (
        FormSubmission.objects.filter(
            inbox_submissions_filter_q(user, eids),
            workflow_state=FormSubmission.WorkflowState.IN_PROGRESS,
            form__deleted_at__isnull=True,
        )
        .distinct()
    )
    if eids is not None:
        base_inbox_qs = base_inbox_qs.filter(form__entity_id__in=eids)

    undo_recent = timezone.now() - UNDO_APPROVE_WINDOW
    completed_recent_pks = (
        SubmissionEvent.objects.filter(
            kind=SubmissionEvent.Kind.WORKFLOW_COMPLETED,
            created_by=user,
            created_at__gte=undo_recent,
        )
        .values_list("submission_id", flat=True)
        .distinct()
    )
    completed_undo_candidates = FormSubmission.objects.filter(
        pk__in=completed_recent_pks,
        workflow_state=FormSubmission.WorkflowState.COMPLETED,
        form__deleted_at__isnull=True,
    ).distinct()
    if eids is not None:
        completed_undo_candidates = completed_undo_candidates.filter(form__entity_id__in=eids)

    return (base_inbox_qs | completed_undo_candidates).distinct()


def inbox_open_count_for_user(user, request=None) -> int:
    """
    Count of submissions in the staff inbox (in progress, assignee or active delegate),
    scoped the same way as the inbox list view.
    """
    from .entity_access import effective_entity_ids
    from .models import FormSubmission

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return 0
    eids = effective_entity_ids(user, request)
    sub_base = FormSubmission.objects.all()
    if eids is not None:
        sub_base = sub_base.filter(form__entity_id__in=eids)
    return (
        sub_base.filter(
            inbox_submissions_filter_q(user, eids),
            workflow_state=FormSubmission.WorkflowState.IN_PROGRESS,
            form__deleted_at__isnull=True,
        )
        .distinct()
        .count()
    )
