"""
Studio access model
-------------------
* **Everyone** can use public routes (home, entity portals, forms, tracking) without signing in.
* **Superusers** can use the full workspace for every organization, ``/manage/super/…``, and Django ``/admin/``.
* **Staff** (``User.is_staff``) use the **staff studio** for organizations they belong to; data is scoped
  to those memberships (or to the superuser session scope when acting as superuser).
* **Non-staff** users who belong to at least one organization get a **portal** at ``/manage/`` (home,
  inbox when they are assignees or delegates, submission search for their connected submissions,
  published forms, and their own submission snapshot).
  Builder tools, responses grid, exports, and org admin use per-organization permissions on
  ``EntityMembership`` (see ``entity_permissions`` and ``studio_capability_required``).
  Staff and superusers still have full workspace access in their organizations.
"""
import json
import mimetypes
import os
import uuid
from urllib.parse import quote
from functools import wraps
from datetime import date, timedelta
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import BigIntegerField, Count, Exists, F, Max, OuterRef, Prefetch, Q, ProtectedError, Subquery, Value
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncDate
from django.template.defaultfilters import date as dj_template_date
from django.template.defaultfilters import linebreaksbr as dj_linebreaksbr
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.text import get_valid_filename
from django.utils.translation import gettext as _, ngettext
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from .entity_access import (
    MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY,
    categories_queryset_for_user,
    delegations_queryset_for_user,
    effective_entity_ids,
    entities_queryset_for_user,
    entity_ids_for_user,
    user_may_access_entity,
    forms_queryset_for_user,
    entity_users_for_entities_search,
    entity_users_for_entity_search,
    users_visible_in_people,
)
from .entity_permissions import (
    user_has_any_entity_permission,
    MANAGE_CATEGORIES,
    MANAGE_DELEGATIONS,
    MANAGE_ENTITY_SETTINGS,
    MANAGE_FORMS,
    MANAGE_PEOPLE,
    EXPORT_RESPONSES,
    VIEW_RESPONSES,
    MANAGE_CATEGORIES_WRITE,
    MANAGE_DELEGATIONS_WRITE,
    MANAGE_ENTITY_SETTINGS_WRITE,
    MANAGE_FORMS_WRITE,
    MANAGE_PEOPLE_WRITE,
    EXPORT_RESPONSES_WRITE,
    VIEW_RESPONSES_WRITE,
    apply_membership_permissions_from_post,
    can_grant_entity_permissions,
    entities_with_permission,
    membership_permissions_for_user,
    people_allowed_entity_ids,
    people_assignable_entities,
    permission_groups_for_entity,
    read_or_write,
    user_has_entity_permission,
)
from .manage_capabilities import studio_capability_required
from .pagination import STUDIO_PER_PAGE_CHOICES, paginate, paginate_sample_forms
from .responses_grid_columns import (
    GRID_SORT_DEFAULT_DESC,
    GRID_SORT_DEFAULT_KEY,
    RESPONSES_GRID_TABLE_ANCHOR,
    all_column_keys_for_form,
    apply_responses_grid_sort,
    build_projected_grid_rows,
    column_catalog,
    parse_column_keys_param,
    parse_grid_sort,
    response_cards_from_rows,
)
from .responses_grid_views import (
    delete_responses_grid_view,
    resolve_active_column_keys,
    responses_grid_views_for_form,
    resolve_share_grid_view,
    save_responses_grid_view,
    set_view_shares,
    share_targets_queryset,
    user_may_access_grid_view,
    user_owns_grid_view,
)
from .submission_responses_grid import (
    MAX_EXPORT_ROWS,
    build_responses_grid_statistics,
    export_pdf_bytes,
    build_submission_timeline_pdf_payload,
    export_timeline_pdf_bytes,
    export_xlsx_bytes,
)


def _studio_portal_can_access(user):
    """Signed-in superuser, or any active user with at least one entity membership."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return bool(entity_ids_for_user(user))


studio_access_required = user_passes_test(
    _studio_portal_can_access,
    login_url=settings.LOGIN_URL,
)


def _staff_can_manage_studio(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_active
        and (user.is_superuser or user.is_staff)
    )


def staff_studio_required(view_func):
    """
    Staff/superuser studio: same portal rule as ``studio_access_required``, plus staff or superuser.
    Authenticated org members who are not staff are redirected to the dashboard with a message
    (avoids bouncing them through the login view with a staff-only ``next`` URL).
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        u = request.user
        if not getattr(u, "is_authenticated", False) or not u.is_active:
            return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
        if not _studio_portal_can_access(u):
            return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
        if not _staff_can_manage_studio(u):
            messages.warning(
                request,
                _(
                    "That area is only for organization administrators. "
                    "Use Home for published forms or Help for guides."
                ),
            )
            return redirect("manage:dashboard")
        return view_func(request, *args, **kwargs)

    return wrapper
superuser_required = user_passes_test(
    lambda u: u.is_authenticated and u.is_superuser,
    login_url=settings.LOGIN_URL,
)
from .models import (
    Entity,
    EntityEmailNotificationTemplate,
    EntityMembership,
    FieldType,
    Form,
    FormCategory,
    FormField,
    FormIntroSlide,
    FormLogo,
    FormSection,
    FormSubmission,
    StaffInboxSubmissionDetailView,
    SubmissionApplicantMessage,
    SubmissionAttachment,
    SubmissionEvent,
    SubmissionPrivateStickyNote,
    SubmissionThreadLastRead,
    SubmissionThreadMessage,
    SubmissionUserHighlight,
    SubmissionUserTag,
    UserSubmissionTask,
    SubmissionValue,
    SupplementaryFormLink,
    SupplementarySubmission,
    USER_SIGNATURE_MAX_PER_USER,
    UserSignature,
    WorkflowDelegation,
    WorkflowStep,
)
from .attachment_utils import (
    attachment_may_delete_on_manage,
    attachment_source_ext_for_pdf,
)
from .pdf_branding import stamp_entity_logo_on_pdf
from .print_merge import (
    PrintMergeError,
    docx_to_pdf_available,
    libreoffice_bytes_to_pdf,
    print_template_merge_capabilities,
    render_submission_document,
)
from .supplementary import ensure_related_invitations
from .workflow_access import (
    applicant_submissions_filter_q,
    delegate_action_suffix,
    form_supports_workflow_decisions,
    inbox_list_queryset,
    inbox_open_count_for_user,
    inbox_submissions_filter_q,
    staff_workflow_thread_filter_q,
    staff_workflow_timeline_filter_q,
    submission_in_portal_search_scope,
    user_may_act_on_submission_workflow,
)
from .workflow_undo import (
    UNDO_APPROVE_MINUTES,
    last_undoable_approve_event,
    perform_undo_last_approve,
)
from .dynamic_forms import build_public_form, build_visibility_rules
from .form_layout import build_public_layout_blocks
from .text_to_form_engine import (
    FormEngineError,
    _unique_form_slug,
    parse_text_to_form_spec,
    persist_parsed_form_spec,
)
from .user_mapping import build_initial_from_mappings
from .context_processors import ai_features_enabled
from .opaque_ids import encode as oid_encode, parse_id as oid_parse
from .views import (
    _entity_visual_ctx,
    _signature_placements_payload,
    _signature_sign_i18n,
    remember_signature_from_placement,
    signature_place_response,
    signature_remove_response,
)
from .sample_forms_library import (
    SAMPLE_CATEGORIES,
    SAMPLE_FORM_SLUGS,
    is_starter_sample_slug,
    is_unclaimed_starter_sample,
)

SAMPLE_FILTER_CATEGORY_SLUGS = frozenset(c[0] for c in SAMPLE_CATEGORIES)
from .staff_forms import (
    StaffCategoryForm,
    StaffEmployeeProfileForm,
    StaffEntityForm,
    EntityEmailNotificationsManageForm,
    StaffFieldForm,
    StaffLogoForm,
    StaffIntroPageForm,
    StaffIntroSlideForm,
    StaffMetaForm,
    StaffOptionalPasswordForm,
    StaffSectionForm,
    StaffSubmissionAttachmentForm,
    StaffSubmissionApplicantEmailForm,
    StaffSubmissionForwardForm,
    StaffSubmissionRouteForm,
    StaffRelatedFormLinkForm,
    StaffWorkflowDelegationForm,
    StaffUserAccountForm,
    StaffUserCreateForm,
    StaffUserSignatureForm,
    StaffWorkflowForm,
)
from .workflow_decision import perform_dynamic_route_decision

def _can_manage_deleted_forms(request) -> bool:
    user = request.user
    return bool(user.is_superuser or user_has_any_entity_permission(user, MANAGE_FORMS_WRITE, request=request))


def _form_for_manage(request, pk, **kwargs):
    visibility = "all" if _can_manage_deleted_forms(request) else "active"
    return get_object_or_404(
        forms_queryset_for_user(request.user, visibility=visibility, request=request).select_related(
            "category",
            "entity",
        ),
        pk=pk,
        **kwargs,
    )


def _require_submission_portal_or_staff(request, submission: FormSubmission) -> None:
    """Staff, view-responses permission, or portal search scope for this submission."""
    u = request.user
    if getattr(u, "is_superuser", False) or getattr(u, "is_staff", False):
        return
    if user_has_entity_permission(
        u,
        submission.form.entity_id,
        *read_or_write(VIEW_RESPONSES),
        request=request,
    ):
        return
    if not submission_in_portal_search_scope(u, submission, request):
        raise Http404()


def _require_submission_timeline_access(request, submission: FormSubmission) -> None:
    """Full-page timeline: portal/staff scope or explicit timeline share."""
    from .timeline_shares import user_may_view_submission_timeline

    if not user_may_view_submission_timeline(request.user, submission, request):
        raise Http404()


def _form_public_absolute_url(request, form_instance) -> str:
    return form_instance.build_public_form_absolute_url(request)


def _form_qrcode_png_bytes(data: str) -> bytes:
    from .qrcode_png import encode_qrcode_png

    return encode_qrcode_png(data)


def _submission_manage_post_redirect(request, pk: int, submission_id: int):
    """
    After workflow POST (e.g. inbox quick approve/reject), optional ``next`` returns to that URL.
    Only allows same-site paths under /manage/ (prevents open redirects).
    """
    next_path = (request.POST.get("next") or "").strip()
    if (
        next_path.startswith("/manage/")
        and not next_path.startswith("//")
        and ".." not in next_path
        and "\n" not in next_path
    ):
        return redirect(next_path)
    return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)


def _workflow_action_flash_key(submission_id: int) -> str:
    return f"mf_wf_action_flash_{submission_id}"


def _set_workflow_action_flash(request, submission_id: int) -> None:
    """After a successful approve/reject, next manage screen hides workflow buttons once."""
    request.session[_workflow_action_flash_key(submission_id)] = True
    request.session.modified = True


def _consume_workflow_action_flash(request, submission_id: int) -> bool:
    """True for a single request after approve/reject (session one-shot)."""
    return bool(request.session.pop(_workflow_action_flash_key(submission_id), False))


def _record_inbox_submission_detail_viewed(request, submission: FormSubmission) -> None:
    """Persist that this user opened manage submission detail (inbox muted star; survives sessions/devices)."""
    StaffInboxSubmissionDetailView.objects.update_or_create(
        user=request.user,
        submission=submission,
        defaults={"seen_at": timezone.now()},
    )


_THREAD_READ_ZERO = Value(0, output_field=BigIntegerField())


def _touch_submission_thread_last_read(request, submission: FormSubmission) -> None:
    """Mark thread messages read through the latest id (clears inbox unread badge for this user)."""
    if not getattr(request.user, "is_authenticated", False):
        return

    mx = (
        SubmissionThreadMessage.objects.filter(submission_id=submission.pk).aggregate(m=Max("id")).get("m")
        or 0
    )
    SubmissionThreadLastRead.objects.update_or_create(
        user=request.user,
        submission=submission,
        defaults={"last_seen_message_id": mx},
    )


def _annotate_has_unread_thread(qs, user):
    from .inbox_filters import annotate_has_unread_thread

    return annotate_has_unread_thread(qs, user)


def _maybe_unpublish(form_instance):
    # Dynamic-routing forms route ad hoc and never need pre-configured steps; only fixed-step
    # forms are unpublished for having none.
    needs_steps = form_instance.routing_mode == Form.RoutingMode.FIXED_STEPS
    if form_instance.is_published and (
        not form_instance.fields.exists() or (needs_steps and not form_instance.workflow_steps.exists())
    ):
        Form.objects.filter(pk=form_instance.pk).update(is_published=False)
        form_instance.is_published = False
        return True
    return False


def _dashboard_forms_layout(request) -> str:
    """Persist list vs grid layout for the home forms section (session + ``?layout=``)."""
    raw = (request.GET.get("layout") or "").strip().lower()
    if raw in ("list", "grid"):
        request.session["dashboard_forms_layout"] = raw
        return raw
    stored = request.session.get("dashboard_forms_layout", "list")
    return stored if stored in ("list", "grid") else "list"


def _dashboard_clear_search_url(
    request, layout: str, *, archive_view: bool, per_page: int
) -> str:
    from urllib.parse import urlencode

    q = {"per_page": str(per_page), "layout": layout}
    if archive_view:
        q["archive"] = "1"
    return f"{reverse('manage:dashboard')}?{urlencode(q)}"


@studio_access_required
def dashboard(request):
    eids = effective_entity_ids(request.user, request)
    applicant_home = (
        request.user.is_authenticated
        and not request.user.is_superuser
        and not request.user.is_staff
    )
    can_archive = _can_manage_deleted_forms(request)
    archive_view = can_archive and request.GET.get("archive") == "1"
    undo_form = None
    undo_pk = oid_parse(request.GET.get("undo"))
    if can_archive and undo_pk:
        undo_form = (
            forms_queryset_for_user(request.user, visibility="deleted", request=request)
            .filter(pk=undo_pk)
            .first()
        )
    forms_visibility = "deleted" if archive_view else "active"
    forms_search_q = (request.GET.get("q") or "").strip()[:200]
    sample_search_q = (request.GET.get("sample_q") or "").strip()[:200]
    sample_category = (request.GET.get("sample_category") or "").strip()
    if sample_category not in SAMPLE_FILTER_CATEGORY_SLUGS:
        sample_category = ""
    wf_prefetch = Prefetch(
        "workflow_steps",
        queryset=WorkflowStep.objects.order_by("order", "id"),
    )
    forms_qs = (
        forms_queryset_for_user(
            request.user,
            visibility=forms_visibility,
            request=request,
            for_lists=not archive_view,
        )
        .select_related("category", "entity")
        .prefetch_related(wf_prefetch)
        .order_by("-updated_at")
    )
    if not archive_view and forms_visibility == "active":
        # Unclaimed starters stay in the samples section; claimed ones appear in Forms for the owner.
        if request.user.is_superuser:
            forms_qs = forms_qs.exclude(slug__in=SAMPLE_FORM_SLUGS, created_by__isnull=True)
        else:
            forms_qs = forms_qs.filter(
                ~Q(slug__in=SAMPLE_FORM_SLUGS) | Q(created_by=request.user)
            )
    if applicant_home and not archive_view:
        forms_qs = forms_qs.filter(is_published=True)
    if forms_search_q:
        forms_qs = forms_qs.filter(
            Q(title__icontains=forms_search_q)
            | Q(slug__icontains=forms_search_q)
            | Q(description__icontains=forms_search_q)
            | Q(category__name__icontains=forms_search_q)
            | Q(entity__name__icontains=forms_search_q)
        )
    forms_page, per_page = paginate(request, forms_qs)

    has_sample_forms = False
    sample_forms_total_count = 0
    sample_forms_category_total = 0
    sample_forms_page = None
    sample_forms_match_count = 0
    if not archive_view and not applicant_home:
        sample_base = (
            forms_queryset_for_user(
                request.user,
                visibility="active",
                request=request,
                for_lists=False,
            )
            .filter(slug__in=SAMPLE_FORM_SLUGS, created_by__isnull=True, deleted_at__isnull=True)
        )
        sample_forms_total_count = sample_base.count()
        has_sample_forms = sample_forms_total_count > 0
        sample_qs = (
            sample_base.select_related("category", "entity")
            .prefetch_related(wf_prefetch)
            .order_by("entity__name", "title")
        )
        if sample_category:
            sample_qs = sample_qs.filter(category__slug=sample_category)
        sample_forms_category_total = (
            sample_base.filter(category__slug=sample_category).count()
            if sample_category
            else sample_forms_total_count
        )
        if sample_search_q:
            sample_qs = sample_qs.filter(title__icontains=sample_search_q)
        if has_sample_forms:
            sample_forms_page = paginate_sample_forms(request, sample_qs)
            sample_forms_match_count = sample_forms_page.paginator.count

    form_scope = {} if eids is None else {"form__entity_id__in": eids}
    sub_base = FormSubmission.objects.filter(**form_scope).filter(form__deleted_at__isnull=True)
    if applicant_home:
        sub_base = sub_base.filter(applicant_submissions_filter_q(request.user))

    active_forms_qs = forms_queryset_for_user(
        request.user, visibility="active", request=request, for_lists=True
    )
    if request.user.is_superuser:
        active_forms_qs = active_forms_qs.exclude(
            slug__in=SAMPLE_FORM_SLUGS, created_by__isnull=True
        )
    else:
        active_forms_qs = active_forms_qs.filter(
            ~Q(slug__in=SAMPLE_FORM_SLUGS) | Q(created_by=request.user)
        )
    if applicant_home:
        active_forms_qs = active_forms_qs.filter(is_published=True)
    total_forms = active_forms_qs.count()
    published_forms = active_forms_qs.filter(is_published=True).count()
    draft_forms = total_forms - published_forms

    total_submissions = sub_base.count()
    inbox_count = (
        0 if applicant_home else inbox_open_count_for_user(request.user, request)
    )

    state_rows = sub_base.values("workflow_state").annotate(c=Count("id"))
    state_counts = {row["workflow_state"]: row["c"] for row in state_rows}
    ws = FormSubmission.WorkflowState
    submissions_in_progress = state_counts.get(ws.IN_PROGRESS, 0)
    submissions_completed = state_counts.get(ws.COMPLETED, 0)
    submissions_rejected = state_counts.get(ws.REJECTED, 0)

    today = timezone.localdate()
    chart_start = today - timedelta(days=29)
    daily_rows = (
        sub_base.filter(submitted_at__date__gte=chart_start)
        .annotate(day=TruncDate("submitted_at", tzinfo=timezone.get_current_timezone()))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    by_day = {}
    for row in daily_rows:
        d = row["day"]
        if hasattr(d, "date"):
            d = d.date()
        by_day[d] = row["count"]

    daily_labels = []
    daily_counts = []
    for i in range(30):
        d = chart_start + timedelta(days=i)
        daily_labels.append(date_format(d, format="M j"))
        daily_counts.append(by_day.get(d, 0))

    chart_data = {
        "dailyLabels": daily_labels,
        "dailyCounts": daily_counts,
        "stateLabels": [_("In progress"), _("Completed"), _("Rejected")],
        "stateCounts": [
            submissions_in_progress,
            submissions_completed,
            submissions_rejected,
        ],
        "chartDatasetLabel": _("Submissions"),
    }

    dash_q = request.GET.copy()
    dash_q.pop("sample_q", None)
    dash_q.pop("sample_category", None)
    dash_q.pop("sample_page", None)
    dashboard_qs_without_sample = dash_q.urlencode()

    sample_category_label = ""
    if sample_category:
        for slug, name, _order in SAMPLE_CATEGORIES:
            if slug == sample_category:
                sample_category_label = name
                break

    from .timeline_shares import shared_timelines_for_user

    shared_timelines = shared_timelines_for_user(request.user, request)

    forms_layout = _dashboard_forms_layout(request)

    return render(
        request,
        "magicforms/manage/dashboard.html",
        {
            "forms_list": forms_page,
            "forms_layout": forms_layout,
            "dashboard_clear_search_url": _dashboard_clear_search_url(
                request,
                forms_layout,
                archive_view=archive_view,
                per_page=per_page,
            ),
            "forms_search_q": forms_search_q,
            "dashboard_archive_view": archive_view,
            "dashboard_can_archive": can_archive,
            "undo_form": undo_form,
            "archived_forms_total": forms_queryset_for_user(
                request.user,
                visibility="deleted",
                request=request,
            ).count()
            if request.user.is_superuser
            else 0,
            "per_page": per_page,
            "per_page_choices": STUDIO_PER_PAGE_CHOICES,
            "stat_total_forms": total_forms,
            "stat_published_forms": published_forms,
            "stat_draft_forms": draft_forms,
            "stat_total_submissions": total_submissions,
            "stat_inbox": inbox_count,
            "stat_submissions_in_progress": submissions_in_progress,
            "stat_submissions_completed": submissions_completed,
            "stat_submissions_rejected": submissions_rejected,
            "chart_data": chart_data,
            "sample_forms_page": sample_forms_page,
            "sample_forms_match_count": sample_forms_match_count,
            "sample_forms_total_count": sample_forms_total_count,
            "has_sample_forms": has_sample_forms,
            "sample_search_q": sample_search_q,
            "sample_category": sample_category,
            "sample_category_label": sample_category_label,
            "sample_category_choices": SAMPLE_CATEGORIES,
            "sample_forms_category_total": sample_forms_category_total,
            "dashboard_qs_without_sample": dashboard_qs_without_sample,
            "dashboard_applicant_mode": applicant_home,
            "shared_timelines": shared_timelines,
        },
    )


@staff_studio_required
@require_POST
def sample_form_claim(request, pk):
    """Claim an unclaimed starter template: set created_by and show it in the main Forms list."""
    form_instance = _form_for_manage(request, pk)
    if not is_starter_sample_slug(form_instance.slug):
        messages.error(request, _("This form is not a starter sample template."))
        return redirect("manage:dashboard")
    if form_instance.created_by_id is not None:
        messages.info(request, _("This starter template was already added to someone’s forms."))
        return redirect("manage:form_detail", pk=form_instance.pk)
    form_instance.created_by = request.user
    form_instance.save(update_fields=["created_by", "updated_at"])
    messages.success(
        request,
        _("“%(title)s” is now in your Forms list. Open it to edit and publish when ready.")
        % {"title": form_instance.title},
    )
    return redirect("manage:form_detail", pk=form_instance.pk)


@studio_access_required
def studio_help(request):
    """Staff guide: building forms, print templates, placeholders, and studio workflows."""
    return render(
        request,
        "magicforms/manage/help.html",
        {
            "docx_pdf_available": docx_to_pdf_available(),
            "new_form_url": reverse("manage:form_create"),
            "from_text_url": reverse("manage:form_generate_from_text"),
        },
    )


def _parse_submitted_date_param(raw: str | None) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _filter_submissions_by_submitted_date(qs, d_from: date | None, d_to: date | None):
    if d_from is not None:
        qs = qs.filter(submitted_at__date__gte=d_from)
    if d_to is not None:
        qs = qs.filter(submitted_at__date__lte=d_to)
    return qs


def _forms_queryset_with_submission_values(user, request):
    """Active forms the user can access that have at least one stored submission value."""
    return (
        forms_queryset_for_user(user, visibility="active", request=request, for_lists=False)
        .filter(deleted_at__isnull=True)
        .annotate(
            _has_submission_values=Exists(
                SubmissionValue.objects.filter(submission__form_id=OuterRef("pk"))
            ),
        )
        .filter(_has_submission_values=True)
        .select_related("entity", "category")
        .order_by("entity__name", "title")
    )


def _enrich_responses_grid_file_cells(
    cells: list[dict],
    submission: FormSubmission,
    fields: list[FormField],
) -> None:
    """Mark file-field cells with a direct URL when an upload exists."""
    by_field = {v.field_id: v for v in submission.values.all()}
    field_by_pk = {f.pk: f for f in fields}
    for cell in cells:
        key = cell.get("key", "")
        if not key.startswith("field:"):
            continue
        try:
            field_pk = int(key.split(":", 1)[1])
        except (TypeError, ValueError):
            continue
        field = field_by_pk.get(field_pk)
        if field is None or field.field_type != FieldType.FILE:
            continue
        sv = by_field.get(field_pk)
        if sv is None or not sv.attachment:
            continue
        cell["is_file"] = True
        cell["file_url"] = sv.attachment.url


def _enrich_response_card_file_pairs(
    cards: list[dict],
    submissions: list[FormSubmission],
    fields: list[FormField],
    column_keys: list[str],
    headers: list[str],
    data_rows: list[list[str]],
) -> None:
    """Add ``file_url`` to card pairs for file uploads (mobile card layout)."""
    skip = {"meta:reference", "meta:applicant", "meta:submitted"}
    field_by_pk = {f.pk: f for f in fields}
    for card, sub, row in zip(cards, submissions, data_rows, strict=True):
        by_field = {v.field_id: v for v in sub.values.all()}
        pairs: list[dict] = []
        for key, label, value in zip(column_keys, headers, row, strict=True):
            if key in skip:
                continue
            file_url = ""
            if key.startswith("field:"):
                try:
                    field_pk = int(key.split(":", 1)[1])
                except (TypeError, ValueError):
                    field_pk = None
                if field_pk is not None:
                    field = field_by_pk.get(field_pk)
                    sv = by_field.get(field_pk)
                    if (
                        field is not None
                        and field.field_type == FieldType.FILE
                        and sv is not None
                        and sv.attachment
                    ):
                        file_url = sv.attachment.url
            pairs.append({"label": label, "value": value, "file_url": file_url})
        card["pairs"] = pairs


def _responses_grid_cell_dicts(
    column_keys: list[str],
    values: list[str],
    *,
    sort_key: str | None = None,
    sort_desc: bool = False,
    sort_url_for_key=None,
) -> list[dict]:
    """Build template cell metadata (ref / meta / field, first-field separator)."""
    first_field = True
    cells: list[dict] = []
    for key, value in zip(column_keys, values, strict=True):
        is_meta = key.startswith("meta:")
        is_ref = key == "meta:reference"
        is_field_first = False
        if not is_meta:
            if first_field:
                is_field_first = True
                first_field = False
        cell: dict = {
            "key": key,
            "value": value,
            "is_ref": is_ref,
            "is_meta": is_meta,
            "is_field_first": is_field_first,
        }
        if sort_url_for_key is not None:
            cell["sort_url"] = sort_url_for_key(key)
            cell["sort_active"] = key == sort_key
            cell["sort_desc"] = bool(sort_desc) if key == sort_key else False
        cells.append(cell)
    return cells


def _format_grid_total(total: float) -> str:
    if float(total).is_integer():
        return f"{int(total):,}"
    return f"{total:,.2f}"


def _responses_grid_totals_row(fields, active_column_keys, subs_qs) -> list[dict]:
    """Footer cells with the sum of each visible Number field, over all filtered
    submissions (not just the current page). Empty list when nothing to total."""
    number_field_by_key = {
        f"field:{f.pk}": f for f in fields if f.field_type == FieldType.NUMBER
    }
    visible_keys = [k for k in active_column_keys if k in number_field_by_key]
    if not visible_keys:
        return []

    # Strip ordering so annotated sort columns don't leak into the __in subquery.
    submission_pks = subs_qs.order_by().values("pk")
    totals: dict[str, str] = {}
    for key in visible_keys:
        fld = number_field_by_key[key]
        total = 0.0
        has_value = False
        raw_values = SubmissionValue.objects.filter(
            field=fld, submission__in=submission_pks
        ).values_list("value", flat=True)
        for raw in raw_values:
            raw = (raw or "").strip().replace(",", "")
            if not raw:
                continue
            try:
                total += float(raw)
            except ValueError:
                continue
            has_value = True
        if has_value:
            totals[key] = _format_grid_total(total)
    if not totals:
        return []

    row_values: list[str] = []
    for idx, key in enumerate(active_column_keys):
        if key in totals:
            row_values.append(totals[key])
        elif idx == 0:
            row_values.append(str(_("Total")))
        else:
            row_values.append("")
    return _responses_grid_cell_dicts(active_column_keys, row_values)


def _responses_grid_query_base(
    *, form_pk, view_pk, cols, submitted_from, submitted_to, sort_key, sort_desc, search_q=""
):
    from urllib.parse import urlencode

    q: dict[str, str] = {"form": oid_encode(oid_parse(form_pk) or 0)}
    if view_pk:
        q["view"] = oid_encode(oid_parse(view_pk) or 0)
    elif cols:
        q["cols"] = cols
    if submitted_from:
        q["submitted_from"] = submitted_from
    if submitted_to:
        q["submitted_to"] = submitted_to
    if search_q:
        q["q"] = search_q
    if sort_key and (sort_key != GRID_SORT_DEFAULT_KEY or sort_desc != GRID_SORT_DEFAULT_DESC):
        q["sort"] = sort_key
        q["order"] = "desc" if sort_desc else "asc"
    return q


def _responses_grid_sort_url(
    form_pk: int,
    column_key: str,
    *,
    active_sort_key: str,
    active_sort_desc: bool,
    view_pk: str = "",
    cols: str = "",
    submitted_from: str = "",
    submitted_to: str = "",
    search_q: str = "",
) -> str:
    from urllib.parse import urlencode

    if column_key == active_sort_key:
        descending = not active_sort_desc
    else:
        descending = False
    q = _responses_grid_query_base(
        form_pk=form_pk,
        view_pk=view_pk,
        cols=cols,
        submitted_from=submitted_from,
        submitted_to=submitted_to,
        sort_key=column_key,
        sort_desc=descending,
        search_q=search_q,
    )
    return f"{reverse('manage:responses_grid')}?{urlencode(q)}#{RESPONSES_GRID_TABLE_ANCHOR}"


def _responses_grid_redirect_url(
    form_pk: int,
    *,
    view_pk: int | None = None,
    cols: str | None = None,
    submitted_from: str = "",
    submitted_to: str = "",
    open_share: bool = False,
    share_view_pk: int | None = None,
    sort_key: str | None = None,
    sort_desc: bool | None = None,
) -> str:
    from urllib.parse import urlencode

    q = _responses_grid_query_base(
        form_pk=form_pk,
        view_pk=str(view_pk) if view_pk else "",
        cols=cols or "",
        submitted_from=submitted_from,
        submitted_to=submitted_to,
        sort_key=sort_key or GRID_SORT_DEFAULT_KEY,
        sort_desc=sort_desc if sort_desc is not None else GRID_SORT_DEFAULT_DESC,
    )
    if open_share:
        q["open_share"] = "1"
    if share_view_pk:
        q["share_view"] = oid_encode(int(share_view_pk))
    return f"{reverse('manage:responses_grid')}?{urlencode(q)}"


@studio_capability_required(*read_or_write(VIEW_RESPONSES), any_entity=True)
def responses_grid(request):
    """Pick a form and browse submission answers in a wide table; export XLSX/PDF."""
    form_qs = _forms_queryset_with_submission_values(request.user, request)
    forms_for_select = list(form_qs)
    form_pk = (request.GET.get("form") or "").strip()
    view_pk = (request.GET.get("view") or "").strip()
    cols_param = (request.GET.get("cols") or "").strip()
    submitted_from = _parse_submitted_date_param(request.GET.get("submitted_from"))
    submitted_to = _parse_submitted_date_param(request.GET.get("submitted_to"))
    grid_search_q = (request.GET.get("q") or "").strip()[:200]
    if submitted_from and submitted_to and submitted_from > submitted_to:
        messages.warning(request, _("That date range is invalid (from is after to). Filters were cleared."))
        submitted_from = None
        submitted_to = None

    selected = None
    fields: list[FormField] = []
    grid_headers: list[str] = []
    grid_rows: list[list[str]] = []
    submissions_page = None
    per_page: int | None = None
    response_cards: list[dict] = []
    active_column_keys: list[str] = []
    active_grid_view = None
    saved_views: list = []
    column_catalog_items: list = []

    grid_display_rows: list[list[dict]] = []
    grid_header_cells: list[dict] = []
    owned_grid_views: list = []
    share_grid_view = None
    shared_with_users: list = []
    open_share_panel = False
    grid_sort_key = GRID_SORT_DEFAULT_KEY
    grid_sort_desc = GRID_SORT_DEFAULT_DESC
    grid_stats = None
    grid_has_email_field = False
    grid_total_cells: list[dict] = []
    if oid_parse(form_pk):
        selected = form_qs.filter(pk=oid_parse(form_pk)).first()
        if not selected:
            messages.error(request, _("Form not found or you do not have access."))
        else:
            fields = list(selected.get_ordered_fields())
            grid_has_email_field = _form_supports_bulk_email(selected)
            saved_views = list(responses_grid_views_for_form(request.user, selected))
            column_catalog_items = column_catalog(fields)
            active_column_keys, active_grid_view = resolve_active_column_keys(
                request.user,
                selected,
                fields,
                view_pk=view_pk,
                cols_param=cols_param,
            )
            grid_sort_key, grid_sort_desc = parse_grid_sort(
                request.GET.get("sort"),
                request.GET.get("order"),
                active_column_keys,
            )
            grid_stats = build_responses_grid_statistics(selected, fields)
            subs_base = (
                selected.submissions.select_related(
                    "submitted_by",
                    "submitted_by__profile",
                    "current_step",
                )
                .prefetch_related(
                    Prefetch("values", queryset=SubmissionValue.objects.select_related("field"))
                )
            )
            subs_base = _filter_submissions_by_submitted_date(subs_base, submitted_from, submitted_to)
            if grid_search_q:
                search_kw = (
                    Q(values__value__icontains=grid_search_q)
                    | Q(values__field__label__icontains=grid_search_q)
                    | Q(submitter_email__icontains=grid_search_q)
                    | Q(submitted_by__username__icontains=grid_search_q)
                    | Q(submitted_by__email__icontains=grid_search_q)
                    | Q(submitted_by__first_name__icontains=grid_search_q)
                    | Q(submitted_by__last_name__icontains=grid_search_q)
                    | Q(current_step__label__icontains=grid_search_q)
                )
                if grid_search_q.isdigit():
                    search_kw |= Q(reference_token__startswith=grid_search_q)
                subs_base = subs_base.filter(search_kw).distinct()
            subs_base = apply_responses_grid_sort(
                subs_base,
                sort_key=grid_sort_key,
                descending=grid_sort_desc,
                fields=fields,
            )
            submissions_page, per_page = paginate(request, subs_base)
            grid_headers, grid_rows = build_projected_grid_rows(
                list(submissions_page.object_list),
                fields,
                active_column_keys,
            )
            response_cards = response_cards_from_rows(
                grid_headers,
                grid_rows,
                column_keys=active_column_keys,
            )
            grid_total_cells = _responses_grid_totals_row(
                fields,
                active_column_keys,
                subs_base,
            )

            owned_grid_views = [v for v in saved_views if v.owner_id == request.user.pk]
            share_grid_view = resolve_share_grid_view(
                request.user,
                saved_views,
                active_view=active_grid_view,
                share_view_pk=(request.GET.get("share_view") or "").strip() or None,
            )
            open_share_panel = (request.GET.get("open_share") or "").strip() == "1"
            if share_grid_view:
                shared_with_users = list(
                    share_grid_view.shares.select_related("user").order_by("user__username")
                )

    for row in grid_rows:
        grid_display_rows.append(_responses_grid_cell_dicts(active_column_keys, row))

    page_submissions = list(submissions_page.object_list) if submissions_page else []
    highlight_map: dict[int, str] = {}
    if page_submissions:
        highlight_map = {
            h.submission_id: h.color
            for h in SubmissionUserHighlight.objects.filter(
                user=request.user,
                submission_id__in=[s.pk for s in page_submissions],
            )
        }
    grid_table_rows = []
    for sub, cells in zip(page_submissions, grid_display_rows):
        if fields:
            _enrich_responses_grid_file_cells(cells, sub, fields)
        grid_table_rows.append(
            {
                "submission_pk": sub.pk,
                "highlight": highlight_map.get(sub.pk, ""),
                "cells": cells,
            }
        )
    if response_cards and page_submissions and fields and grid_headers:
        _enrich_response_card_file_pairs(
            response_cards,
            page_submissions,
            fields,
            active_column_keys,
            grid_headers,
            grid_rows,
        )

    sort_url_view = view_pk if active_grid_view else ""
    sort_url_cols = cols_param if not active_grid_view and cols_param else ""
    sort_submitted_from = submitted_from.isoformat() if submitted_from else ""
    sort_submitted_to = submitted_to.isoformat() if submitted_to else ""

    if grid_headers and selected:
        grid_header_cells = _responses_grid_cell_dicts(
            active_column_keys,
            grid_headers,
            sort_key=grid_sort_key,
            sort_desc=grid_sort_desc,
            sort_url_for_key=lambda col_key: _responses_grid_sort_url(
                selected.pk,
                col_key,
                active_sort_key=grid_sort_key,
                active_sort_desc=grid_sort_desc,
                view_pk=sort_url_view,
                cols=sort_url_cols,
                submitted_from=sort_submitted_from,
                submitted_to=sort_submitted_to,
                search_q=grid_search_q,
            ),
        )
    else:
        grid_header_cells = []

    ctx = {
        "forms_for_select": forms_for_select,
        "selected_form": selected,
        "grid_headers": grid_headers,
        "grid_header_cells": grid_header_cells,
        "grid_fields": fields,
        "grid_rows": grid_rows,
        "grid_display_rows": grid_display_rows,
        "grid_table_rows": grid_table_rows,
        "grid_highlight_colors": [
            (key, label)
            for key, label in SubmissionUserHighlight.COLOR_CHOICES
            if key in SubmissionUserHighlight.RESPONSES_GRID_COLOR_KEYS
        ],
        "response_cards": response_cards,
        "owned_grid_views": owned_grid_views,
        "share_grid_view": share_grid_view,
        "shared_with_users": shared_with_users,
        "open_share_panel": open_share_panel,
        "submissions_page": submissions_page,
        "per_page": per_page,
        "per_page_choices": STUDIO_PER_PAGE_CHOICES,
        "grid_stats": grid_stats,
        "responses_submitted_from": submitted_from.isoformat() if submitted_from else "",
        "responses_submitted_to": submitted_to.isoformat() if submitted_to else "",
        "responses_search_q": grid_search_q,
        "grid_has_email_field": grid_has_email_field,
        "grid_total_cells": grid_total_cells,
        "active_column_keys": active_column_keys,
        "active_column_keys_csv": ",".join(active_column_keys),
        "active_grid_view": active_grid_view,
        "saved_grid_views": saved_views,
        "column_catalog": column_catalog_items,
        "user_owns_active_grid_view": bool(
            active_grid_view and user_owns_grid_view(request.user, active_grid_view)
        ),
        "all_column_keys_csv": ",".join(all_column_keys_for_form(fields)) if fields else "",
        "grid_sort_key": grid_sort_key,
        "grid_sort_desc": grid_sort_desc,
        "grid_sort_query": (
            f"&sort={grid_sort_key}&order={'desc' if grid_sort_desc else 'asc'}"
            if grid_sort_key != GRID_SORT_DEFAULT_KEY or grid_sort_desc != GRID_SORT_DEFAULT_DESC
            else ""
        ),
    }
    if selected is not None:
        ctx["form_obj"] = selected
    return render(request, "magicforms/manage/responses_grid.html", ctx)


@studio_capability_required(*read_or_write(VIEW_RESPONSES), any_entity=True)
@require_POST
def responses_grid_view_save(request):
    """Save or update a named column layout for the responses grid."""
    form_pk = oid_parse(request.POST.get("form"))
    if not form_pk:
        messages.error(request, _("Choose a form first."))
        return redirect("manage:responses_grid")

    selected = _forms_queryset_with_submission_values(request.user, request).filter(pk=form_pk).first()
    if not selected:
        raise Http404()

    fields = list(selected.get_ordered_fields())
    raw_keys = request.POST.getlist("column_keys")
    if not raw_keys:
        raw_keys = [
            p.strip()
            for p in (request.POST.get("column_keys_csv") or "").split(",")
            if p.strip()
        ]
    name = (request.POST.get("view_name") or "").strip()
    view_id_raw = (request.POST.get("view_id") or "").strip()
    view_id = int(view_id_raw) if view_id_raw.isdigit() else None
    set_default = (request.POST.get("set_default") or "").strip() == "1"
    submitted_from = (request.POST.get("submitted_from") or "").strip()
    submitted_to = (request.POST.get("submitted_to") or "").strip()

    from django.db import IntegrityError

    try:
        view = save_responses_grid_view(
            request.user,
            selected,
            name=name,
            column_keys=raw_keys,
            fields=fields,
            view_id=view_id,
            set_default=set_default,
        )
    except ValueError:
        messages.error(request, _("Enter a name for this view."))
        return redirect(
            _responses_grid_redirect_url(
                oid_parse(form_pk),
                cols=",".join(parse_column_keys_param(",".join(raw_keys), fields)),
                submitted_from=submitted_from,
                submitted_to=submitted_to,
            )
        )
    except IntegrityError:
        messages.error(request, _("Could not save this view. Try a different name."))
        return redirect(
            _responses_grid_redirect_url(
                oid_parse(form_pk),
                cols=",".join(parse_column_keys_param(",".join(raw_keys), fields)),
                submitted_from=submitted_from,
                submitted_to=submitted_to,
            )
        )

    messages.success(request, _("Saved view “%(name)s”.") % {"name": view.name})
    return redirect(
        _responses_grid_redirect_url(
            oid_parse(form_pk),
            view_pk=view.pk,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
        )
    )


@studio_capability_required(*read_or_write(VIEW_RESPONSES), any_entity=True)
@require_POST
def responses_grid_view_delete(request, view_pk):
    from .models import ResponsesGridView

    view = get_object_or_404(
        ResponsesGridView.objects.select_related("form"),
        pk=view_pk,
    )
    if not _forms_queryset_with_submission_values(request.user, request).filter(pk=view.form_id).exists():
        raise Http404()
    form_pk = view.form_id
    submitted_from = (request.POST.get("submitted_from") or "").strip()
    submitted_to = (request.POST.get("submitted_to") or "").strip()
    try:
        delete_responses_grid_view(request.user, view)
    except PermissionError:
        messages.error(request, _("You can only delete views you created."))
        return redirect(
            _responses_grid_redirect_url(
                form_pk,
                view_pk=view_pk,
                submitted_from=submitted_from,
                submitted_to=submitted_to,
            )
        )
    messages.success(request, _("Deleted saved view."))
    return redirect(
        _responses_grid_redirect_url(form_pk, submitted_from=submitted_from, submitted_to=submitted_to)
    )


@studio_capability_required(*read_or_write(VIEW_RESPONSES), any_entity=True)
@require_POST
def responses_grid_view_share(request, view_pk):
    from .models import ResponsesGridView

    view = get_object_or_404(
        ResponsesGridView.objects.select_related("form"),
        pk=view_pk,
    )
    if not _forms_queryset_with_submission_values(request.user, request).filter(pk=view.form_id).exists():
        raise Http404()
    if not user_owns_grid_view(request.user, view):
        messages.error(request, _("Only the view owner can change sharing."))
        return redirect(_responses_grid_redirect_url(view.form_id, view_pk=view_pk))

    raw_ids = request.POST.getlist("share_user_ids")
    user_ids = [int(x) for x in raw_ids if str(x).isdigit()]
    submitted_from = (request.POST.get("submitted_from") or "").strip()
    submitted_to = (request.POST.get("submitted_to") or "").strip()
    set_view_shares(request.user, view, user_ids=user_ids)
    messages.success(request, _("Sharing updated."))
    return redirect(
        _responses_grid_redirect_url(
            view.form_id,
            view_pk=view.pk,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
            open_share=True,
            share_view_pk=view.pk,
        )
    )


@studio_capability_required(EXPORT_RESPONSES_WRITE, any_entity=True)
def responses_grid_export(request):
    """Download all answers for a form as XLSX or PDF (up to MAX_EXPORT_ROWS)."""
    fmt = (request.GET.get("fmt") or "").strip().lower()
    form_pk = (request.GET.get("form") or "").strip()
    if fmt not in ("xlsx", "pdf"):
        return HttpResponse(_("Unsupported format."), status=400, content_type="text/plain; charset=utf-8")
    if not oid_parse(form_pk):
        return HttpResponse(_("Choose a form."), status=400, content_type="text/plain; charset=utf-8")

    selected = _forms_queryset_with_submission_values(request.user, request).filter(pk=oid_parse(form_pk)).select_related("entity").first()
    if not selected:
        raise Http404(_("Form not found."))

    submitted_from = _parse_submitted_date_param(request.GET.get("submitted_from"))
    submitted_to = _parse_submitted_date_param(request.GET.get("submitted_to"))
    if submitted_from and submitted_to and submitted_from > submitted_to:
        submitted_from, submitted_to = None, None

    fields = list(selected.get_ordered_fields())
    view_pk = (request.GET.get("view") or "").strip()
    cols_param = (request.GET.get("cols") or "").strip()
    column_keys, _active_view = resolve_active_column_keys(
        request.user,
        selected,
        fields,
        view_pk=view_pk,
        cols_param=cols_param,
    )
    grid_sort_key, grid_sort_desc = parse_grid_sort(
        request.GET.get("sort"),
        request.GET.get("order"),
        column_keys,
    )

    subs_qs = selected.submissions.select_related(
        "submitted_by",
        "submitted_by__profile",
        "current_step",
    ).prefetch_related(Prefetch("values", queryset=SubmissionValue.objects.select_related("field")))
    subs_qs = _filter_submissions_by_submitted_date(subs_qs, submitted_from, submitted_to)
    subs_qs = apply_responses_grid_sort(
        subs_qs,
        sort_key=grid_sort_key,
        descending=grid_sort_desc,
        fields=fields,
    )
    subs = list(subs_qs[: MAX_EXPORT_ROWS + 1])
    truncated = len(subs) > MAX_EXPORT_ROWS
    subs = subs[:MAX_EXPORT_ROWS]
    headers, data_rows = build_projected_grid_rows(subs, fields, column_keys)
    stem = get_valid_filename(f"{selected.slug}_responses")[:120] or "responses"

    try:
        if fmt == "xlsx":
            raw = export_xlsx_bytes(headers, data_rows, selected.slug[:31])
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"{stem}.xlsx"
        else:
            title = f"{selected.entity.name} — {selected.title}"
            raw = export_pdf_bytes(str(title), headers, data_rows, entity=selected.entity)
            content_type = "application/pdf"
            filename = f"{stem}.pdf"
    except RuntimeError as exc:
        return HttpResponse(str(exc), status=503, content_type="text/plain; charset=utf-8")

    resp = FileResponse(BytesIO(raw), as_attachment=True, filename=filename)
    resp["Content-Type"] = content_type
    if truncated:
        resp["X-MagicForms-Export-Truncated"] = "1"
    return resp


@studio_access_required
def user_search(request):
    """JSON user search. Query ``q``; optional ``form`` + ``scope=entity`` for org members (workflow assignees)."""
    q = (request.GET.get("q") or "").strip()
    form_pk = oid_parse(request.GET.get("form"))
    scope = (request.GET.get("scope") or "").strip().lower()
    if form_pk:
        visibility = "all" if request.user.is_superuser else "active"
        selected = (
            forms_queryset_for_user(request.user, visibility=visibility, request=request)
            .filter(pk=form_pk)
            .first()
        )
        if selected and scope == "entity" and selected.entity_id:
            qs = entity_users_for_entity_search(selected.entity_id, q)[:50]
        elif selected:
            qs = share_targets_queryset(request.user, selected, q=q).exclude(pk=request.user.pk)[:50]
        else:
            qs = entity_users_for_entities_search(request.user, q, request=request)
    else:
        qs = entity_users_for_entities_search(request.user, q, request=request)
    results = []
    for u in qs:
        label = u.get_username()
        if u.get_full_name():
            label += f" — {u.get_full_name()}"
        job_title = getattr(getattr(u, "profile", None), "job_title", "") or ""
        if job_title:
            label += f" · {job_title}"
        if u.email:
            label += f" ({u.email})"
        if u.is_superuser:
            label += f" ({_('Super admin')})"
        elif u.is_staff:
            label += f" ({_('Organization admin')})"
        else:
            label += f" ({_('End user')})"
        results.append({"id": u.pk, "text": label})
    return JsonResponse({"results": results})


def _manager_queryset(User, exclude_pk=None, actor=None, request=None):
    if actor is not None and not actor.is_superuser:
        if can_grant_entity_permissions(actor):
            eids = effective_entity_ids(actor, request)
            if eids is None:
                qs = User.objects.filter(is_active=True)
            elif not eids:
                qs = User.objects.none()
            else:
                uids = EntityMembership.objects.filter(entity_id__in=eids).values_list(
                    "user_id", flat=True
                ).distinct()
                qs = User.objects.filter(pk__in=uids, is_active=True)
        else:
            eids = entities_with_permission(actor, *read_or_write(MANAGE_PEOPLE), request=request)
            if not eids:
                qs = User.objects.none()
            else:
                uids = EntityMembership.objects.filter(entity_id__in=eids).values_list(
                    "user_id", flat=True
                ).distinct()
                qs = User.objects.filter(pk__in=uids, is_active=True)
        qs = qs.order_by("username")
    else:
        qs = User.objects.filter(is_active=True).order_by("username")
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs


def _restrict_user_account_form(form, editor):
    if can_grant_entity_permissions(editor):
        return form
    if "is_staff" in form.fields:
        del form.fields["is_staff"]
    return form


def _people_entity_context(editor, user=None, request=None):
    ents = list(people_assignable_entities(editor, request))
    if not ents:
        return {}
    member_entity_ids: set[int] = set()
    perm_map: dict[int, dict[str, bool]] = {}
    if user:
        member_entity_ids = set(
            EntityMembership.objects.filter(user=user).values_list("entity_id", flat=True)
        )
        if can_grant_entity_permissions(editor):
            perm_map = membership_permissions_for_user(user)
    grant = can_grant_entity_permissions(editor)
    entity_rows = []
    for ent in ents:
        row = {
            "entity": ent,
            "member_checked": ent.pk in member_entity_ids,
            "permission_groups": permission_groups_for_entity(ent.pk, perm_map) if grant else [],
        }
        entity_rows.append(row)
    return {
        "people_entity_rows": entity_rows,
        "can_grant_entity_permissions": grant,
    }


def _selected_people_entity_ids(editor, post, request) -> list[int]:
    allowed = people_allowed_entity_ids(editor, request)
    raw = [int(x) for x in post.getlist("entity_ids") if str(x).isdigit()]
    picked = [eid for eid in raw if eid in allowed]
    if not picked and len(allowed) == 1:
        picked = list(allowed)
    return picked


def _sync_people_memberships(editor, target_user, post, request) -> tuple[bool, str]:
    picked = _selected_people_entity_ids(editor, post, request)
    if not picked:
        return False, _("Select at least one organization for this user.")
    allowed = people_allowed_entity_ids(editor, request)
    EntityMembership.objects.filter(
        user=target_user,
        entity_id__in=allowed,
    ).exclude(entity_id__in=picked).delete()
    for eid in picked:
        EntityMembership.objects.get_or_create(user=target_user, entity_id=eid)
    if can_grant_entity_permissions(editor):
        apply_membership_permissions_from_post(
            editor,
            target_user,
            post,
            allowed_entity_ids=allowed,
        )
    return True, ""


def _user_edit_page_context(User, user, signature_add_form=None, editor=None, request=None):
    mq = _manager_queryset(User, exclude_pk=user.pk, actor=editor, request=request)
    signatures = list(user.signatures.order_by("sort_order", "id"))
    if signature_add_form is None:
        signature_add_form = StaffUserSignatureForm()
    account_form = _restrict_user_account_form(StaffUserAccountForm(instance=user), editor)
    ctx = {
        "is_create": False,
        "edit_user": user,
        "account_form": account_form,
        "profile_form": StaffEmployeeProfileForm(instance=user.profile, manager_queryset=mq),
        "pw_form": StaffOptionalPasswordForm(),
        "signature_add_form": signature_add_form,
        "signatures": signatures,
        "signature_limit": USER_SIGNATURE_MAX_PER_USER,
    }
    if editor:
        ctx.update(_people_entity_context(editor, user=user, request=request))
    return ctx


@studio_capability_required(*read_or_write(MANAGE_PEOPLE), any_entity=True)
def user_list(request):
    User = get_user_model()
    q = (request.GET.get("q") or "").strip()
    role = (request.GET.get("role") or "").strip().lower()
    qs = users_visible_in_people(request.user, request=request).select_related("profile")
    if role == "staff":
        qs = qs.filter(is_staff=True, is_superuser=False)
    elif role == "end_user":
        qs = qs.filter(is_staff=False, is_superuser=False)
    elif role == "superuser":
        qs = qs.filter(is_superuser=True)
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(profile__employee_number__icontains=q)
            | Q(profile__civil_id__icontains=q)
            | Q(profile__job_title__icontains=q)
        )
    users_page, per_page = paginate(request, qs)
    return render(
        request,
        "magicforms/manage/user_list.html",
        {
            "users": users_page,
            "search_q": q,
            "role_filter": role,
            "per_page": per_page,
            "per_page_choices": STUDIO_PER_PAGE_CHOICES,
        },
    )


@studio_capability_required(MANAGE_PEOPLE_WRITE, any_entity=True)
def user_add(request):
    User = get_user_model()
    mq = _manager_queryset(User, actor=request.user, request=request)
    people_ctx = _people_entity_context(request.user, request=request)
    if request.method == "POST":
        user_form = StaffUserCreateForm(request.POST)
        if not can_grant_entity_permissions(request.user) and "is_staff" in user_form.fields:
            del user_form.fields["is_staff"]
        profile_form = StaffEmployeeProfileForm(request.POST, manager_queryset=mq)
        if user_form.is_valid() and profile_form.is_valid():
            if not _selected_people_entity_ids(request.user, request.POST, request):
                messages.error(request, _("Select at least one organization for this user."))
                uctx = {
                    "is_create": True,
                    "edit_user": None,
                    "user_form": user_form,
                    "profile_form": profile_form,
                    "people_orgs_section_open": True,
                    **people_ctx,
                }
                return render(request, "magicforms/manage/user_form.html", uctx)
            with transaction.atomic():
                user = user_form.save()
                if not can_grant_entity_permissions(request.user):
                    User.objects.filter(pk=user.pk).update(is_staff=False)
                profile = user.profile
                for name, value in profile_form.cleaned_data.items():
                    setattr(profile, name, value)
                profile.save()
                _sync_people_memberships(request.user, user, request.POST, request)
            messages.success(
                request,
                _("Created account for %(username)s.") % {"username": user.get_username()},
            )
            return redirect("manage:user_edit", pk=user.pk)
        uctx = {
            "is_create": True,
            "edit_user": None,
            "user_form": user_form,
            "profile_form": profile_form,
            **people_ctx,
        }
        return render(request, "magicforms/manage/user_form.html", uctx)
    user_form = StaffUserCreateForm()
    if not can_grant_entity_permissions(request.user) and "is_staff" in user_form.fields:
        del user_form.fields["is_staff"]
    ctx = {
        "is_create": True,
        "edit_user": None,
        "user_form": user_form,
        "profile_form": StaffEmployeeProfileForm(manager_queryset=mq),
        **people_ctx,
    }
    return render(request, "magicforms/manage/user_form.html", ctx)


@studio_capability_required(MANAGE_PEOPLE_WRITE, any_entity=True)
def user_edit(request, pk):
    User = get_user_model()
    user = get_object_or_404(
        users_visible_in_people(request.user, request=request).select_related("profile"),
        pk=pk,
    )
    profile = user.profile
    mq = _manager_queryset(User, exclude_pk=user.pk, actor=request.user)
    if request.method == "POST":
        sig_action = (request.POST.get("signature_action") or "").strip()
        if sig_action == "add":
            if user.signatures.count() >= USER_SIGNATURE_MAX_PER_USER:
                messages.error(
                    request,
                    _("Each user can have at most %(max)d signature images.")
                    % {"max": USER_SIGNATURE_MAX_PER_USER},
                )
                return render(
                    request,
                    "magicforms/manage/user_form.html",
                    _user_edit_page_context(User, user, editor=request.user, request=request),
                )
            sig_form = StaffUserSignatureForm(request.POST, request.FILES)
            if sig_form.is_valid():
                obj = sig_form.save(commit=False)
                obj.user = user
                mx = user.signatures.aggregate(m=Max("sort_order"))["m"]
                obj.sort_order = (mx if mx is not None else -1) + 1
                obj.save()
                messages.success(request, _("Signature image added."))
                return redirect("manage:user_edit", pk=pk)
            return render(
                request,
                "magicforms/manage/user_form.html",
                _user_edit_page_context(User, user, sig_form, editor=request.user, request=request),
            )
        if sig_action == "set_primary":
            sid = (request.POST.get("signature_id") or "").strip()
            if sid.isdigit() and UserSignature.assign_primary(user, int(sid)):
                messages.success(request, _("Primary signature updated."))
            else:
                messages.error(request, _("That signature was not found."))
            return redirect("manage:user_edit", pk=pk)
        if sig_action == "delete":
            messages.error(
                request,
                _(
                    "Removing signature images is not available from this page. "
                    "You can add images or set the primary; the user can remove their own on “My signatures”."
                ),
            )
            return redirect("manage:user_edit", pk=pk)

        account_form = _restrict_user_account_form(
            StaffUserAccountForm(request.POST, instance=user),
            request.user,
        )
        profile_form = StaffEmployeeProfileForm(
            request.POST,
            instance=profile,
            manager_queryset=mq,
        )
        pw_form = StaffOptionalPasswordForm(request.POST)
        ok_a = account_form.is_valid()
        ok_p = profile_form.is_valid()
        ok_w = pw_form.is_valid()
        pwd = (pw_form.cleaned_data.get("password1") or "") if ok_w else ""
        people_orgs_open = False
        if ok_a and ok_p and ok_w:
            if user.pk == request.user.pk and not account_form.cleaned_data.get("is_active"):
                account_form.add_error(
                    "is_active",
                    _("You cannot deactivate your own account here."),
                )
            elif not _selected_people_entity_ids(request.user, request.POST, request):
                messages.error(request, _("Select at least one organization for this user."))
                people_orgs_open = True
            else:
                try:
                    with transaction.atomic():
                        account_form.save()
                        if not can_grant_entity_permissions(request.user):
                            User.objects.filter(pk=user.pk).update(is_staff=False)
                        profile_form.save()
                        _sync_people_memberships(request.user, user, request.POST, request)
                        if pwd:
                            validate_password(pwd, user=user)
                            user.set_password(pwd)
                            user.save(update_fields=["password"])
                except ValidationError as exc:
                    for msg in exc.messages:
                        pw_form.add_error("password1", msg)
                else:
                    messages.success(request, _("User updated."))
                    return redirect("manage:user_edit", pk=pk)
        ctx = {
            "is_create": False,
            "edit_user": user,
            "account_form": account_form,
            "profile_form": profile_form,
            "pw_form": pw_form,
            "signature_add_form": StaffUserSignatureForm(),
            "signatures": list(user.signatures.order_by("sort_order", "id")),
            "signature_limit": USER_SIGNATURE_MAX_PER_USER,
            "people_orgs_section_open": people_orgs_open,
            **_people_entity_context(request.user, user=user, request=request),
        }
        return render(request, "magicforms/manage/user_form.html", ctx)
    return render(
        request,
        "magicforms/manage/user_form.html",
        _user_edit_page_context(User, user, editor=request.user, request=request),
    )


@studio_access_required
def inbox(request):
    """
    Submissions whose current workflow step lists this user as an assignee,
    or an assignee who has delegated to this user.

    The form filter lists only forms that currently have at least one such submission
    (not every form in the organization).
    """
    from .inbox_ai import inbox_ai_available
    from .inbox_filters import apply_inbox_list_filters, inbox_filter_options
    from .submission_tasks import user_task_submission_ids

    user = request.user
    combined_inbox_qs = inbox_list_queryset(user, request)
    opts = inbox_filter_options(user, request)
    inbox_form_ids = opts["inbox_form_ids"]
    inbox_total_count = combined_inbox_qs.count()
    steps_for_filter = opts["steps"]

    qs = _annotate_has_unread_thread(combined_inbox_qs, user).select_related(
        "form", "form__entity", "current_step", "submitted_by"
    ).prefetch_related(
        "current_step__assigned_users",
        Prefetch(
            "values",
            queryset=SubmissionValue.objects.select_related("field").order_by(
                "field__order", "field_id"
            ),
        ),
        Prefetch(
            "user_tags",
            queryset=SubmissionUserTag.objects.filter(user=user).order_by("label"),
            to_attr="_prefetched_private_user_tags",
        ),
        Prefetch(
            "user_highlights",
            queryset=SubmissionUserHighlight.objects.filter(user=user),
            to_attr="_prefetched_user_highlights",
        ),
    )

    qs, filter_meta = apply_inbox_list_filters(qs, request, inbox_form_ids=inbox_form_ids)
    search_q = filter_meta["search_q"]
    form_filter_id = filter_meta["form_filter_id"]
    step_filter_id = filter_meta["step_filter_id"]
    sort_key = filter_meta["sort_key"]
    inbox_has_filters = filter_meta["has_filters"]

    highlight_filter = (request.GET.get("highlight") or "").strip().lower()
    if highlight_filter == "any":
        qs = qs.filter(user_highlights__user=user)
    elif highlight_filter == "none":
        qs = qs.exclude(user_highlights__user=user)
    elif highlight_filter in SubmissionUserHighlight.COLOR_KEYS:
        qs = qs.filter(user_highlights__user=user, user_highlights__color=highlight_filter)
    else:
        highlight_filter = ""
    if highlight_filter:
        inbox_has_filters = True

    submissions_page, per_page = paginate(request, qs)

    from .responses_grid_applicant import attach_studio_list_applicant

    page_submissions = list(submissions_page.object_list)
    form_ids = {s.form_id for s in page_submissions}
    forms_with_workflow: set[int] = set()
    if form_ids:
        # Fixed-step forms only: a dynamic-routing form may still have old WorkflowStep rows left
        # over from before it was switched, and those no longer drive anything — showing the quick
        # approve/reject buttons for it would silently do nothing when clicked.
        forms_with_workflow = set(
            WorkflowStep.objects.filter(
                form_id__in=form_ids, form__routing_mode=Form.RoutingMode.FIXED_STEPS
            )
            .values_list("form_id", flat=True)
            .distinct()
        )
    for _s in page_submissions:
        pr = getattr(_s, "_prefetched_private_user_tags", None)
        _s.private_tag_labels = [t.label for t in pr] if pr else []
        hls = getattr(_s, "_prefetched_user_highlights", None)
        _s.inbox_highlight_color = hls[0].color if hls else ""
        attach_studio_list_applicant(_s)
        _s.inbox_workflow_quick_enabled = (_s.form_id in forms_with_workflow) and user_may_act_on_submission_workflow(
            user, _s
        )
        undo_ev = last_undoable_approve_event(user, _s)
        _s.inbox_undo_last_approve_visible = undo_ev is not None
        _s.inbox_undo_event_pk = undo_ev.pk if undo_ev else None
    inbox_detail_seen_submission_ids: set[int] = set()
    if page_submissions:
        inbox_detail_seen_submission_ids = set(
            StaffInboxSubmissionDetailView.objects.filter(
                user=user,
                submission_id__in=[s.pk for s in page_submissions],
            ).values_list("submission_id", flat=True)
        )

    return render(
        request,
        "magicforms/manage/inbox.html",
        {
            "submissions": submissions_page,
            "inbox_total_count": inbox_total_count,
            "inbox_filtered_count": submissions_page.paginator.count,
            "inbox_has_filters": inbox_has_filters,
            "per_page": per_page,
            "per_page_choices": STUDIO_PER_PAGE_CHOICES,
            "search_q": search_q,
            "sort_key": sort_key,
            "form_filter_id": form_filter_id,
            "step_filter_id": step_filter_id,
            "forms_for_filter": opts["forms"],
            "steps_for_filter": steps_for_filter,
            "inbox_detail_seen_submission_ids": inbox_detail_seen_submission_ids,
            "highlight_filter": highlight_filter,
            "highlight_colors": SubmissionUserHighlight.COLOR_CHOICES,
            "inbox_ai_available": ai_features_enabled() and inbox_ai_available(),
            "user_task_submission_ids": user_task_submission_ids(request.user),
            "workflow_undo_window_minutes": UNDO_APPROVE_MINUTES,
        },
    )


@studio_access_required
@require_POST
def inbox_ai_chat(request):
    """JSON: natural-language inbox search for the current user."""
    if not ai_features_enabled():
        raise Http404()
    from .inbox_ai import run_inbox_ai_chat

    question = (request.POST.get("question") or "").strip()
    if not question:
        return JsonResponse(
            {"ok": False, "message": _("Enter a question to search your inbox.")},
            status=400,
        )
    if len(question) > 500:
        question = question[:500]
    payload = run_inbox_ai_chat(request.user, request, question)
    return JsonResponse(payload)


INBOX_BATCH_MAX = 200


def _inbox_batch_redirect(request):
    """Return to the posted ``next`` (same-site /manage/ path only) or the inbox."""
    next_path = (request.POST.get("next") or "").strip()
    if (
        next_path.startswith("/manage/")
        and not next_path.startswith("//")
        and ".." not in next_path
        and "\n" not in next_path
    ):
        return redirect(next_path)
    return redirect("manage:inbox")


def _apply_inbox_workflow_decision(
    request, submission: FormSubmission, decision: str, comment: str
) -> str | None:
    """
    Approve or reject one submission with the same checks as the manage detail page.
    Returns "rejected", "completed", or "advanced"; None when the submission was skipped
    (already decided, no current step, the user may not act on it, or the form is set to
    dynamic routing, which pauses workflow actions until that engine ships).
    """
    form_instance = submission.form
    if not form_instance.workflow_steps.exists():
        return None
    if not form_supports_workflow_decisions(form_instance):
        return None
    outcome: str | None = None
    with transaction.atomic():
        fresh = (
            FormSubmission.objects.select_related("current_step")
            .prefetch_related("current_step__assigned_users")
            .select_for_update()
            .get(pk=submission.pk)
        )
        if fresh.workflow_state != FormSubmission.WorkflowState.IN_PROGRESS:
            return None
        if not fresh.current_step_id:
            return None
        if not user_may_act_on_submission_workflow(request.user, fresh):
            return None

        delegate_suffix = delegate_action_suffix(request.user, fresh)

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
                created_by=request.user,
            )
            outcome = "rejected"
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
                    created_by=request.user,
                )
                outcome = "completed"
            else:
                fresh.current_step = next_step
                fresh.save(update_fields=["current_step", "updated_at"])
                SubmissionEvent.objects.create(
                    submission=fresh,
                    kind=SubmissionEvent.Kind.STEP_APPROVED,
                    step=next_step,
                    message=event_message(f'Approved; advanced to "{next_step.label}".'),
                    created_by=request.user,
                )
                outcome = "advanced"
            ensure_related_invitations(fresh)
    return outcome


@studio_access_required
@require_POST
def inbox_batch_action(request):
    """Approve or reject several inbox submissions in one action."""
    from .notification_emails import queue_after_submission_event

    decision = (request.POST.get("batch_decision") or "").strip()
    if decision not in ("approve", "reject"):
        messages.error(request, _("Choose Approve or Reject for the batch action."))
        return _inbox_batch_redirect(request)

    comment = (request.POST.get("batch_comment") or "").strip()[:800]
    if decision == "reject" and not comment:
        messages.error(request, _("Enter a reason for rejection before submitting."))
        return _inbox_batch_redirect(request)
    if decision == "approve":
        comment = ""

    ids: list[int] = []
    for raw in request.POST.getlist("submission_ids")[:INBOX_BATCH_MAX]:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        messages.error(request, _("Select at least one submission."))
        return _inbox_batch_redirect(request)

    # Only submissions currently in this user's inbox can be acted on.
    submissions = list(
        inbox_list_queryset(request.user, request)
        .filter(pk__in=ids)
        .select_related("form")
    )
    skipped = len(ids) - len(submissions)

    processed = 0
    for submission in submissions:
        outcome = _apply_inbox_workflow_decision(request, submission, decision, comment)
        if outcome is None:
            skipped += 1
            continue
        processed += 1
        latest_event = (
            SubmissionEvent.objects.filter(submission_id=submission.pk)
            .order_by("-pk")
            .first()
        )
        if latest_event is not None:
            queue_after_submission_event(
                submission,
                latest_event,
                request=request,
                workflow_decision=decision,
                workflow_decision_comment=comment,
                staff_user=request.user,
            )
        _set_workflow_action_flash(request, submission.pk)

    if processed:
        if decision == "reject":
            messages.success(
                request,
                ngettext(
                    "%(n)d submission rejected; workflow stopped there.",
                    "%(n)d submissions rejected; workflow stopped there.",
                    processed,
                )
                % {"n": processed},
            )
        else:
            messages.success(
                request,
                ngettext(
                    "%(n)d submission approved. You can undo each approval for %(minutes)d minutes using Undo approve.",
                    "%(n)d submissions approved. You can undo each approval for %(minutes)d minutes using Undo approve.",
                    processed,
                )
                % {"n": processed, "minutes": UNDO_APPROVE_MINUTES},
            )
    if skipped:
        messages.info(
            request,
            ngettext(
                "%(n)d submission was skipped (already updated or not actionable by you).",
                "%(n)d submissions were skipped (already updated or not actionable by you).",
                skipped,
            )
            % {"n": skipped},
        )
    return _inbox_batch_redirect(request)


@studio_access_required
@require_POST
def inbox_highlight(request):
    """JSON: set or clear this user's private highlight color on an inbox submission."""
    sid_raw = (request.POST.get("submission_id") or "").strip()
    color = (request.POST.get("color") or "").strip().lower()
    if not sid_raw.isdigit():
        return JsonResponse({"ok": False, "message": _("Invalid submission.")}, status=400)
    if color and color not in SubmissionUserHighlight.COLOR_KEYS:
        return JsonResponse({"ok": False, "message": _("Unknown highlight color.")}, status=400)
    submission = (
        inbox_list_queryset(request.user, request).filter(pk=int(sid_raw)).first()
    )
    if submission is None:
        return JsonResponse(
            {"ok": False, "message": _("Submission not found in your inbox.")},
            status=404,
        )
    if color:
        SubmissionUserHighlight.objects.update_or_create(
            user=request.user,
            submission=submission,
            defaults={"color": color},
        )
    else:
        SubmissionUserHighlight.objects.filter(
            user=request.user, submission=submission
        ).delete()
    return JsonResponse({"ok": True, "color": color})


@studio_capability_required(*read_or_write(VIEW_RESPONSES), any_entity=True)
@require_POST
def responses_grid_highlight(request):
    """JSON: set or clear this user's private highlight color on a responses-grid row."""
    sid_raw = (request.POST.get("submission_id") or "").strip()
    color = (request.POST.get("color") or "").strip().lower()
    if not sid_raw.isdigit():
        return JsonResponse({"ok": False, "message": _("Invalid submission.")}, status=400)
    if color and color not in SubmissionUserHighlight.COLOR_KEYS:
        return JsonResponse({"ok": False, "message": _("Unknown highlight color.")}, status=400)
    submission = (
        FormSubmission.objects.filter(
            pk=int(sid_raw),
            form__in=_forms_queryset_with_submission_values(request.user, request),
        ).first()
    )
    if submission is None:
        return JsonResponse(
            {"ok": False, "message": _("Submission not found or you do not have access.")},
            status=404,
        )
    if color:
        SubmissionUserHighlight.objects.update_or_create(
            user=request.user,
            submission=submission,
            defaults={"color": color},
        )
    else:
        SubmissionUserHighlight.objects.filter(
            user=request.user, submission=submission
        ).delete()
    return JsonResponse({"ok": True, "color": color})


RESPONSES_BULK_EMAIL_MAX = 100


def _form_supports_bulk_email(form) -> bool:
    """Bulk email is offered when applicant addresses can be resolved: an email
    form field, submitter emails on file, or signed-in applicant accounts."""
    if form.fields.filter(field_type=FieldType.EMAIL).exists():
        return True
    if form.submissions.exclude(submitter_email="").exists():
        return True
    return (
        form.submissions.filter(submitted_by__isnull=False)
        .exclude(submitted_by__email="")
        .exists()
    )


def _responses_grid_back(request):
    """Return to the posted ``next`` (same-site /manage/ path only) or the grid."""
    next_path = (request.POST.get("next") or "").strip()
    if (
        next_path.startswith("/manage/")
        and not next_path.startswith("//")
        and ".." not in next_path
        and "\n" not in next_path
    ):
        return redirect(next_path)
    return redirect("manage:responses_grid")


@studio_capability_required(*read_or_write(VIEW_RESPONSES), any_entity=True)
@require_POST
def responses_grid_bulk_email(request):
    """Send the same email to the applicant address of each selected grid row."""
    from .entity_email import entity_email_notifications_ready
    from .submission_applicant_email import default_applicant_email, send_applicant_email

    form_pk = oid_parse(request.POST.get("form"))
    if not form_pk:
        messages.error(request, _("Choose a form first."))
        return _responses_grid_back(request)
    selected = (
        _forms_queryset_with_submission_values(request.user, request)
        .filter(pk=form_pk)
        .first()
    )
    if not selected:
        messages.error(request, _("Form not found or you do not have access."))
        return _responses_grid_back(request)
    if not _form_supports_bulk_email(selected):
        messages.error(
            request,
            _("Bulk email is unavailable: no email field or applicant addresses on this form."),
        )
        return _responses_grid_back(request)

    mail_ok, mail_block = entity_email_notifications_ready(selected.entity)
    if not mail_ok:
        messages.error(request, mail_block)
        return _responses_grid_back(request)

    subject = (request.POST.get("subject") or "").strip()[:200]
    body = (request.POST.get("body") or "").strip()[:5000]
    if not subject or not body:
        messages.error(request, _("Enter a subject and a message for the bulk email."))
        return _responses_grid_back(request)

    ids: list[int] = []
    for raw in request.POST.getlist("submission_ids")[:RESPONSES_BULK_EMAIL_MAX]:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        messages.error(request, _("Select at least one submission."))
        return _responses_grid_back(request)

    submissions = list(
        selected.submissions.filter(pk__in=ids)
        .select_related("current_step", "submitted_by")
        .prefetch_related(
            Prefetch("values", queryset=SubmissionValue.objects.select_related("field"))
        )
    )

    reply_to = (request.user.email or "").strip() or None
    sent = 0
    no_email = 0
    failed = 0
    for submission in submissions:
        to_addr, _src, _lbl = default_applicant_email(submission)
        if not to_addr:
            no_email += 1
            continue
        try:
            send_applicant_email(
                submission,
                to_email=to_addr,
                subject=subject,
                body=body,
                reply_to=reply_to,
            )
        except Exception:
            failed += 1
            continue
        sent += 1
        SubmissionEvent.objects.create(
            submission=submission,
            kind=SubmissionEvent.Kind.NOTE,
            step=submission.current_step if submission.current_step_id else None,
            message=_("Email sent to applicant (%(addr)s): %(subject)s")
            % {"addr": to_addr, "subject": subject[:120]},
            created_by=request.user,
        )

    if sent:
        messages.success(
            request,
            ngettext(
                "Email sent for %(n)d submission.",
                "Email sent for %(n)d submissions.",
                sent,
            )
            % {"n": sent},
        )
    if no_email:
        messages.warning(
            request,
            ngettext(
                "%(n)d submission was skipped (no email address found).",
                "%(n)d submissions were skipped (no email address found).",
                no_email,
            )
            % {"n": no_email},
        )
    if failed:
        messages.error(
            request,
            ngettext(
                "Sending failed for %(n)d submission. Check organization email settings.",
                "Sending failed for %(n)d submissions. Check organization email settings.",
                failed,
            )
            % {"n": failed},
        )
    if not (sent or no_email or failed):
        messages.error(request, _("No matching submissions were found."))
    return _responses_grid_back(request)


def _user_submission_task_for_manage(user, submission: FormSubmission):
    from .submission_tasks import task_due_urgency

    row = UserSubmissionTask.objects.filter(
        submission_id=submission.pk,
        user_id=user.pk,
    ).first()
    if row is not None and not row.is_done:
        row.due_urgency = task_due_urgency(row.due_date)
    elif row is not None:
        row.due_urgency = ""
    return row


def _submission_task_redirect(request, form_pk: int, submission_id: int):
    next_path = (request.POST.get("next") or "").strip()
    if (
        next_path.startswith("/manage/")
        and not next_path.startswith("//")
        and ".." not in next_path
        and "\n" not in next_path
    ):
        return redirect(next_path)
    return redirect("manage:submission_manage_detail", pk=form_pk, submission_id=submission_id)


@studio_access_required
@require_POST
def submission_task_action(request, form_pk, submission_id):
    """Add, remove, or toggle done on the current user's submission task list."""
    from django.utils.dateparse import parse_date

    from .submission_tasks import (
        add_submission_task,
        remove_submission_task,
        set_submission_task_due_date,
        toggle_submission_task_done,
        user_may_task_submission,
    )

    form_instance = _form_for_manage(request, form_pk)
    submission = get_object_or_404(
        FormSubmission.objects.select_related("form"),
        pk=submission_id,
        form=form_instance,
        form__deleted_at__isnull=True,
    )
    if not user_may_task_submission(request.user, submission, request):
        raise Http404()

    action = (request.POST.get("task_action") or "").strip()
    note = (request.POST.get("task_note") or "").strip()

    due_date = None
    if action in ("add", "set_due_date"):
        due_raw = (request.POST.get("task_due_date") or "").strip()
        if due_raw:
            due_date = parse_date(due_raw)
            if due_date is None:
                messages.error(request, _("Enter a valid deadline date."))
                if (request.POST.get("redirect_tasks") or "").strip() == "1":
                    show = "1" if (request.POST.get("show_done") or "").strip() == "1" else ""
                    url = reverse("manage:task_list")
                    if show:
                        url += "?show_done=1"
                    return redirect(url)
                return _submission_task_redirect(request, form_pk, submission_id)

    if action == "add":
        created = add_submission_task(
            request.user, submission, note=note, due_date=due_date
        )[0]
        if created:
            messages.success(request, _("Added to your task list."))
        else:
            messages.info(request, _("Already on your task list."))
    elif action == "remove":
        if remove_submission_task(request.user, submission):
            messages.success(request, _("Removed from your task list."))
        else:
            messages.info(request, _("Not on your task list."))
    elif action == "toggle_done":
        new_done = toggle_submission_task_done(request.user, submission)
        if new_done is None:
            messages.error(request, _("Not on your task list."))
        elif new_done:
            messages.success(request, _("Marked task as done."))
        else:
            messages.success(request, _("Marked task as to do."))
    elif action == "set_due_date":
        if set_submission_task_due_date(request.user, submission, due_date):
            if due_date:
                messages.success(request, _("Deadline saved."))
            else:
                messages.success(request, _("Deadline cleared."))
        else:
            messages.error(request, _("Not on your task list."))
    else:
        messages.error(request, _("Unknown task action."))

    if (request.POST.get("redirect_tasks") or "").strip() == "1":
        show = "1" if (request.POST.get("show_done") or "").strip() == "1" else ""
        url = reverse("manage:task_list")
        if show:
            url += "?show_done=1"
        return redirect(url)
    return _submission_task_redirect(request, form_pk, submission_id)


@studio_access_required
def task_list(request):
    """Personal to-do list of submissions the user chose to track."""
    from .submission_tasks import open_task_count_for_user, task_due_urgency, tasks_for_user

    show_done = (request.GET.get("show_done") or "").strip() == "1"
    task_rows = list(tasks_for_user(request.user, include_done=show_done))
    for row in task_rows:
        row.due_urgency = "" if row.is_done else task_due_urgency(row.due_date)
    open_count = open_task_count_for_user(request.user)

    return render(
        request,
        "magicforms/manage/task_list.html",
        {
            "task_rows": task_rows,
            "show_done": show_done,
            "open_count": open_count,
        },
    )


@studio_access_required
def submission_search(request):
    """
    Search submissions tied to the user: applicant, current-step assignee (incl. delegate),
    or staff actions on the submission timeline (workflow path).
    """
    user = request.user
    eids = effective_entity_ids(user, request)

    relation = (request.GET.get("relation") or "any").strip()
    if relation == "assignee":
        relation = "workflow"
    if relation not in ("any", "applicant", "workflow"):
        relation = "any"

    q_applicant = applicant_submissions_filter_q(user)
    q_assignee = inbox_submissions_filter_q(user, eids)
    q_timeline = staff_workflow_timeline_filter_q(user, eids)
    q_thread = staff_workflow_thread_filter_q(user, eids)

    if relation == "any":
        q_rel = q_applicant | q_assignee | q_timeline | q_thread
    elif relation == "applicant":
        q_rel = q_applicant
    else:
        q_rel = q_assignee | q_timeline | q_thread

    qs = (
        FormSubmission.objects.filter(q_rel, form__deleted_at__isnull=True)
        .distinct()
        .select_related("form", "form__entity", "current_step", "submitted_by")
        .prefetch_related(
            "current_step__assigned_users",
            Prefetch(
                "values",
                queryset=SubmissionValue.objects.select_related("field").order_by(
                    "field__order", "field_id"
                ),
            ),
        )
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

    fid = oid_parse(request.GET.get("form"))
    form_filter_id = None
    if fid:
        if forms_queryset_for_user(user, request=request).filter(pk=fid).exists():
            qs = qs.filter(form_id=fid)
            form_filter_id = fid

    from .inbox_filters import build_assistant_keyword_q

    search_q = (request.GET.get("q") or "").strip()[:200]
    field_name = (request.GET.get("field_name") or "").strip()[:80]
    if search_q:
        if field_name:
            qs = qs.filter(
                values__field__name=field_name,
                values__value__icontains=search_q,
            ).distinct()
        else:
            qs = qs.filter(build_assistant_keyword_q(search_q, user)).distinct()

    submitted_from = _parse_submitted_date_param(request.GET.get("submitted_from"))
    submitted_to = _parse_submitted_date_param(request.GET.get("submitted_to"))
    if submitted_from and submitted_to and submitted_from > submitted_to:
        submitted_from, submitted_to = submitted_to, submitted_from
    qs = _filter_submissions_by_submitted_date(qs, submitted_from, submitted_to)

    cat_raw = (request.GET.get("category") or "").strip()
    if cat_raw.isdigit():
        qs = qs.filter(form__category_id=int(cat_raw))

    tag_filter_raw = (request.GET.get("tag") or "").strip()[:80]
    tag_filter = ""
    if tag_filter_raw:
        tag_filter = SubmissionUserTag.normalize_label(tag_filter_raw)
        if tag_filter:
            qs = qs.filter(user_tags__user=user, user_tags__label=tag_filter).distinct()

    sort_key = (request.GET.get("sort") or "submitted_at_desc").strip()
    order_map = {
        "submitted_at_desc": ("-submitted_at",),
        "submitted_at_asc": ("submitted_at",),
        "updated_at_desc": ("-updated_at",),
        "updated_at_asc": ("updated_at",),
        "form_title": ("form__title", "-submitted_at"),
        "form_title_desc": ("-form__title", "-submitted_at"),
    }
    if sort_key not in order_map:
        sort_key = "submitted_at_desc"
    qs = qs.order_by(*order_map[sort_key])

    qs = qs.prefetch_related(
        Prefetch(
            "user_tags",
            queryset=SubmissionUserTag.objects.filter(user=user).order_by("label"),
            to_attr="_prefetched_private_user_tags",
        )
    )

    qs = _annotate_has_unread_thread(qs, user)

    submissions_page, per_page = paginate(request, qs)

    page_pks = [s.pk for s in submissions_page.object_list]
    assignee_pk_set: set[int] = set()
    timeline_pk_set: set[int] = set()
    if page_pks:
        assignee_pk_set = set(
            FormSubmission.objects.filter(pk__in=page_pks)
            .filter(inbox_submissions_filter_q(user, eids))
            .values_list("pk", flat=True)
        )
        from .models import SubmissionEvent

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
        tev = SubmissionEvent.objects.filter(
            submission_id__in=page_pks,
            created_by=user,
            kind__in=kinds,
        )
        timeline_pk_set = set(tev.values_list("submission_id", flat=True).distinct())

    from .responses_grid_applicant import attach_studio_list_applicant

    for s in submissions_page.object_list:
        pr = getattr(s, "_prefetched_private_user_tags", None)
        s.private_tag_labels = [t.label for t in pr] if pr else []
        attach_studio_list_applicant(s)
        roles = []
        if s.submitted_by_id == user.pk:
            roles.append(_("Applicant"))
        else:
            ue = (user.email or "").strip().lower()
            se = (s.submitter_email or "").strip().lower()
            if ue and se and ue == se:
                roles.append(_("Applicant (email)"))
        if s.pk in assignee_pk_set:
            roles.append(_("Assignee"))
        if s.pk in timeline_pk_set:
            roles.append(_("Workflow"))
        s.search_role_labels = roles

    page_submissions = list(submissions_page.object_list)
    inbox_detail_seen_submission_ids: set[int] = set()
    if page_submissions:
        inbox_detail_seen_submission_ids = set(
            StaffInboxSubmissionDetailView.objects.filter(
                user=user,
                submission_id__in=[s.pk for s in page_submissions],
            ).values_list("submission_id", flat=True)
        )

    forms_for_filter = forms_queryset_for_user(user, visibility="active", request=request).order_by(
        "entity__name", "title"
    )

    user_tag_suggestions = list(
        SubmissionUserTag.objects.filter(user=user)
        .values_list("label", flat=True)
        .distinct()
        .order_by("label")[:400]
    )

    from .submission_tasks import user_task_submission_ids

    return render(
        request,
        "magicforms/manage/submission_search.html",
        {
            "submissions": submissions_page,
            "per_page": per_page,
            "per_page_choices": STUDIO_PER_PAGE_CHOICES,
            "relation": relation,
            "workflow_state": wf,
            "search_q": search_q,
            "sort_key": sort_key,
            "forms_for_filter": forms_for_filter,
            "form_filter_id": form_filter_id,
            "workflow_states": FormSubmission.WorkflowState,
            "inbox_detail_seen_submission_ids": inbox_detail_seen_submission_ids,
            "tag_filter": tag_filter,
            "tag_filter_raw": tag_filter_raw,
            "user_tag_suggestions": user_tag_suggestions,
            "submitted_from": submitted_from.isoformat() if submitted_from else "",
            "submitted_to": submitted_to.isoformat() if submitted_to else "",
            "user_task_submission_ids": user_task_submission_ids(request.user),
            "workflow_undo_window_minutes": UNDO_APPROVE_MINUTES,
        },
    )


@studio_capability_required(MANAGE_FORMS_WRITE, any_entity=True)
def form_create(request):
    eids = effective_entity_ids(request.user, request)
    if eids is not None and not eids:
        messages.error(
            request,
            _(
                "Your account is not assigned to any organization. Ask a superuser to add you to an entity."
            ),
        )
        return redirect("manage:dashboard")
    if request.method == "POST":
        f = StaffMetaForm(request.POST, request.FILES, staff_user=request.user, request=request)
        if f.is_valid():
            obj = f.save(commit=False)
            obj.created_by = request.user
            obj.save()
            if _maybe_unpublish(obj):
                messages.warning(
                    request,
                    _(
                        "Publishing turned off until you add at least one field and one workflow step."
                    ),
                )
            else:
                messages.success(request, _("Form created."))
            return redirect("manage:form_detail", pk=obj.pk)
    else:
        f = StaffMetaForm(staff_user=request.user, request=request)
    return render(request, "magicforms/manage/form_create.html", {"form": f})


@studio_capability_required(*read_or_write(MANAGE_CATEGORIES), any_entity=True)
def category_list(request):
    categories_qs = (
        categories_queryset_for_user(request.user, request=request)
        .annotate(
            form_count=Count("forms", filter=Q(forms__deleted_at__isnull=True)),
        )
        .order_by("entity__name", "order", "name")
    )
    categories_page, per_page = paginate(request, categories_qs)
    return render(
        request,
        "magicforms/manage/category_list.html",
        {
            "categories": categories_page,
            "per_page": per_page,
            "per_page_choices": STUDIO_PER_PAGE_CHOICES,
        },
    )


@studio_capability_required(MANAGE_CATEGORIES_WRITE, any_entity=True)
def category_add(request):
    eids = effective_entity_ids(request.user, request)
    if eids is not None and not eids:
        messages.error(
            request,
            _(
                "Your account is not assigned to any organization. Ask a superuser to add you to an entity."
            ),
        )
        return redirect("manage:dashboard")
    if request.method == "POST":
        f = StaffCategoryForm(request.POST, staff_user=request.user, request=request)
        if f.is_valid():
            f.save()
            messages.success(request, _("Category created."))
            return redirect("manage:category_list")
    else:
        f = StaffCategoryForm(staff_user=request.user, request=request)
    return render(
        request,
        "magicforms/manage/category_form.html",
        {"form": f, "mode": "add"},
    )


def _entity_for_text_generate(request):
    """Pick target entity for text-to-form (POST). Returns None if ambiguous or not allowed."""
    eids = effective_entity_ids(request.user, request)
    if eids is not None and not eids:
        return None
    choices = list(entities_queryset_for_user(request.user, request=request))
    if not choices:
        return None
    if len(choices) == 1:
        return choices[0]
    raw = (request.POST.get("entity") or "").strip()
    if raw.isdigit():
        ent = Entity.objects.filter(pk=int(raw), is_active=True).first()
        if ent and (eids is None or ent.pk in eids):
            return ent
    return None


@studio_capability_required(MANAGE_FORMS_WRITE, any_entity=True)
def form_generate_from_text(request):
    if not ai_features_enabled():
        raise Http404()
    eids = effective_entity_ids(request.user, request)
    if eids is not None and not eids:
        messages.error(
            request,
            _(
                "Your account is not assigned to any organization. Ask a superuser to add you to an entity."
            ),
        )
        return redirect("manage:dashboard")
    entity_choices = list(entities_queryset_for_user(request.user, request=request))

    if request.method == "POST":
        text = (request.POST.get("description") or "").strip()
        if not text:
            messages.error(request, _("Describe your form and fields in the text area first."))
            return render(
                request,
                "magicforms/manage/form_generate_from_text.html",
                {"description": "", "entity_choices": entity_choices},
            )
        entity = _entity_for_text_generate(request)
        if entity is None:
            messages.error(request, _("Choose which organization this draft form belongs to."))
            return render(
                request,
                "magicforms/manage/form_generate_from_text.html",
                {"description": text, "entity_choices": entity_choices},
            )
        try:
            spec, warnings, backend = parse_text_to_form_spec(text)
            form_obj = persist_parsed_form_spec(spec, request.user, entity)
        except FormEngineError as exc:
            messages.error(request, str(exc))
            return render(
                request,
                "magicforms/manage/form_generate_from_text.html",
                {"description": text, "entity_choices": entity_choices},
            )
        for w in warnings:
            messages.warning(request, _(w))
        messages.success(
            request,
            _('Form “%(title)s” was created using the %(backend)s parser. You can edit fields, workflow, and publishing next.')
            % {"title": form_obj.title, "backend": backend},
        )
        return redirect("manage:form_detail", pk=form_obj.pk)

    return render(
        request,
        "magicforms/manage/form_generate_from_text.html",
        {"description": "", "entity_choices": entity_choices},
    )


def _copy_form_file_field(dst_form: Form, field_name: str, src_file) -> None:
    """Copy a ``FileField`` from ``src_file`` onto ``dst_form`` (saved with ``update_fields``)."""
    if not src_file:
        return
    fname = os.path.basename(src_file.name)
    with src_file.open("rb") as fh:
        getattr(dst_form, field_name).save(fname, ContentFile(fh.read()), save=False)
    dst_form.save(update_fields=[field_name, "updated_at"])


def _duplicate_form_for_manage(src: Form, user) -> Form:
    """
    Clone ``src`` into a new draft form (same entity): structure, files, logos, and outgoing
    related-form links. Submissions and inbound related links are not copied.
    """
    title = (src.title + _(" (copy)"))[:255]
    slug = _unique_form_slug(title, src.entity)
    with transaction.atomic():
        new_form = Form.objects.create(
            entity_id=src.entity_id,
            title=title,
            slug=slug,
            description=src.description,
            submission_deadline=src.submission_deadline,
            category_id=src.category_id,
            is_published=False,
            one_time_submit=src.one_time_submit,
            is_for_public=src.is_for_public,
            allow_submission_forward=src.allow_submission_forward,
            hide_from_form_lists=src.hide_from_form_lists,
            created_by=user if getattr(user, "is_authenticated", False) else None,
            deleted_at=None,
            public_share_key=None,
        )
        _copy_form_file_field(new_form, "print_template", src.print_template)
        _copy_form_file_field(new_form, "print_template_odt", src.print_template_odt)

        section_map: dict[int, int] = {}
        for sec in src.sections.order_by("order", "id"):
            ns = FormSection.objects.create(
                form=new_form,
                order=sec.order,
                title=sec.title,
                description=sec.description,
                starts_collapsed=sec.starts_collapsed,
            )
            section_map[sec.pk] = ns.pk

        field_map: dict[int, int] = {}
        fields_qs = list(src.fields.order_by("order", "id"))
        for ff in fields_qs:
            nf = FormField(
                form=new_form,
                order=ff.order,
                field_type=ff.field_type,
                name=ff.name,
                mapping_key=ff.mapping_key,
                label=ff.label,
                hint=ff.hint,
                help_text=ff.help_text,
                placeholder=ff.placeholder,
                required=ff.required,
                choices_text=ff.choices_text,
                options_layout=ff.options_layout,
                inline=ff.inline,
                visibility_show_when_values=ff.visibility_show_when_values,
                section_id=section_map.get(ff.section_id) if ff.section_id else None,
                validation_min_length=ff.validation_min_length,
                validation_max_length=ff.validation_max_length,
                validation_must_contain=ff.validation_must_contain,
                validation_must_not_contain=ff.validation_must_not_contain,
                validation_must_equal=ff.validation_must_equal,
                validation_regex=ff.validation_regex,
                validation_integer_only=ff.validation_integer_only,
                validation_decimal_min=ff.validation_decimal_min,
                validation_decimal_max=ff.validation_decimal_max,
                validation_date_after=ff.validation_date_after,
                validation_date_before=ff.validation_date_before,
                validation_unique_value=ff.validation_unique_value,
            )
            nf.save()
            field_map[ff.pk] = nf.pk

        for ff in fields_qs:
            old_vid = ff.visibility_control_field_id
            if not old_vid:
                continue
            new_vid = field_map.get(old_vid)
            if not new_vid:
                continue
            FormField.objects.filter(pk=field_map[ff.pk]).update(visibility_control_field_id=new_vid)

        step_map: dict[int, int] = {}
        steps_qs = list(src.workflow_steps.order_by("order", "id"))
        for st in steps_qs:
            ns = WorkflowStep.objects.create(
                form=new_form,
                order=st.order,
                slug=st.slug,
                label=st.label,
                description=st.description,
            )
            step_map[st.pk] = ns.pk
            ns.assigned_users.set(st.assigned_users.all())

        for link in SupplementaryFormLink.objects.filter(parent_form=src).select_related("trigger_step"):
            new_tid = step_map.get(link.trigger_step_id)
            if not new_tid:
                continue
            SupplementaryFormLink.objects.create(
                parent_form=new_form,
                child_form_id=link.child_form_id,
                trigger_step_id=new_tid,
            )

        for logo in src.logos.order_by("header_slot", "id"):
            nl = FormLogo(form=new_form, header_slot=logo.header_slot)
            with logo.image.open("rb") as fh:
                nl.image.save(os.path.basename(logo.image.name), ContentFile(fh.read()), save=True)

    return new_form


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def form_duplicate(request, pk):
    src = _form_for_manage(request, pk)
    if src.deleted_at:
        messages.error(
            request,
            _("Archived forms cannot be duplicated. Restore the form first, then duplicate it."),
        )
        return redirect("manage:form_detail", pk=pk)
    new_form = _duplicate_form_for_manage(src, request.user)
    messages.success(
        request,
        _("Form duplicated. The copy is a draft; review settings and publishing when you are ready."),
    )
    return redirect("manage:form_detail", pk=new_form.pk)


@studio_capability_required(*read_or_write(MANAGE_FORMS))
def form_detail(request, pk):
    form_instance = _form_for_manage(request, pk)
    can_archive = request.user.is_superuser or user_has_entity_permission(
        request.user, form_instance.entity_id, MANAGE_FORMS_WRITE, request=request
    )
    public_url = _form_public_absolute_url(request, form_instance)
    hub_stats = {
        "fields": form_instance.fields.count(),
        "workflow_steps": form_instance.workflow_steps.count(),
        "submissions": FormSubmission.objects.filter(form=form_instance).count(),
        "logos": form_instance.logos.count(),
    }
    return render(
        request,
        "magicforms/manage/form_detail.html",
        {
            "can_archive": can_archive,
            "form_obj": form_instance,
            "public_url": public_url,
            "hub_stats": hub_stats,
            "show_sample_claim": is_unclaimed_starter_sample(form_instance),
        },
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_GET
def form_preview(request, pk):
    """Staff-only GET preview of the public respondent layout (drafts and unpublished forms included)."""
    visibility = "all" if request.user.is_superuser else "active"
    form_def = get_object_or_404(
        forms_queryset_for_user(request.user, visibility=visibility, request=request)
        .select_related("category", "entity")
        .prefetch_related(
            Prefetch(
                "logos",
                queryset=FormLogo.objects.order_by("header_slot", "id"),
            )
        ),
        pk=pk,
    )
    if not form_def.get_ordered_fields().exists():
        messages.info(
            request,
            _(
                "Add at least one field to preview this form. The preview matches the live layout once fields exist."
            ),
        )
        return redirect("manage:form_detail", pk=pk)

    FormClass = build_public_form(form_def)
    mapping_initial = build_initial_from_mappings(request, FormClass._magicforms_fields_def)
    form = FormClass(initial=mapping_initial)
    layout_blocks = build_public_layout_blocks(
        form, FormClass._magicforms_fields_def, form_def
    )
    visibility_rules = build_visibility_rules(FormClass._magicforms_fields_def)

    return render(
        request,
        "magicforms/form_public.html",
        {
            "form_def": form_def,
            "form": form,
            "layout_blocks": layout_blocks,
            "visibility_rules": visibility_rules,
            "related_mode": False,
            "studio_form_preview": True,
            **_entity_visual_ctx(form_def.entity),
        },
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def form_qrcode_image(request, pk):
    """PNG QR encoding the public form URL (studio staff / superuser only)."""
    form_instance = _form_for_manage(request, pk)
    url = _form_public_absolute_url(request, form_instance)
    try:
        png = _form_qrcode_png_bytes(url)
    except ImportError as exc:
        raise Http404(
            _("QR code generation is not available. Install the %(pkg)s package on the server.")
            % {"pkg": "qrcode"}
        ) from exc
    resp = HttpResponse(png, content_type="image/png")
    resp["Cache-Control"] = "private, max-age=300"
    return resp


@studio_capability_required(MANAGE_FORMS_WRITE)
def form_qrcode(request, pk):
    """Page with QR and copyable link to the live form (studio staff / superuser only)."""
    form_instance = _form_for_manage(request, pk)
    public_url = _form_public_absolute_url(request, form_instance)
    title_plain = str(form_instance.title)
    share_subject = _("Form link: %(title)s") % {"title": title_plain}
    share_body = _(
        "Please use this link to open the form \"%(title)s\":\n\n%(url)s"
    ) % {"title": title_plain, "url": public_url}
    share_mailto = "mailto:?subject=" + quote(share_subject, safe="") + "&body=" + quote(share_body, safe="")
    share_whatsapp = "https://wa.me/?text=" + quote(share_body, safe="")
    return render(
        request,
        "magicforms/manage/form_qrcode.html",
        {
            "form_obj": form_instance,
            "public_url": public_url,
            "share_mailto": share_mailto,
            "share_whatsapp": share_whatsapp,
        },
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def form_share_key_action(request, pk):
    """Enable, rotate, or clear the optional ``?share=`` secret (invalidates old QR codes)."""
    form_instance = _form_for_manage(request, pk)
    act = (request.POST.get("share_key_action") or "").strip()
    if act == "enable":
        typed = (request.POST.get("share_key_confirm") or "").strip().lower()
        if typed != "confirm":
            return redirect(f"{reverse('manage:form_qrcode', kwargs={'pk': pk})}?share_confirm=invalid")
        if form_instance.public_share_key is None:
            Form.objects.filter(pk=form_instance.pk).update(
                public_share_key=uuid.uuid4(),
                updated_at=timezone.now(),
            )
            messages.success(
                request,
                _(
                    "Secure share link is on. New QR codes and links include a secret; old links without it no longer open this form."
                ),
            )
        else:
            messages.info(request, _("A secure share link is already enabled."))
    elif act == "regenerate":
        if form_instance.public_share_key is None:
            messages.error(request, _("Turn on a secure share link first, then you can rotate it."))
        else:
            Form.objects.filter(pk=form_instance.pk).update(
                public_share_key=uuid.uuid4(),
                updated_at=timezone.now(),
            )
            messages.success(
                request,
                _("Share secret rotated. Old QR codes, posters, and bookmarks with the previous link no longer work."),
            )
    elif act == "disable":
        Form.objects.filter(pk=form_instance.pk).update(
            public_share_key=None,
            updated_at=timezone.now(),
        )
        messages.success(
            request,
            _("Secure share link turned off. The public form URL works again without a secret query parameter."),
        )
    else:
        messages.error(request, _("Unknown action."))
    return redirect("manage:form_qrcode", pk=pk)


@studio_capability_required(MANAGE_FORMS_WRITE)
def related_link_list(request, pk):
    form_instance = _form_for_manage(request, pk)
    links = (
        SupplementaryFormLink.objects.filter(parent_form=form_instance)
        .select_related("child_form", "trigger_step")
        .order_by("trigger_step__order", "child_form__title")
    )
    return render(
        request,
        "magicforms/manage/related_form_list.html",
        {"form_obj": form_instance, "links": links},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def related_link_add(request, pk):
    parent_form = _form_for_manage(request, pk)
    if request.method == "POST":
        link_form = StaffRelatedFormLinkForm(request.POST, parent_form=parent_form)
        if link_form.is_valid():
            link_form.save()
            messages.success(request, _("Related form link saved."))
            return redirect("manage:related_link_list", pk=pk)
    else:
        link_form = StaffRelatedFormLinkForm(parent_form=parent_form)
    return render(
        request,
        "magicforms/manage/related_link_form.html",
        {"form_obj": parent_form, "link_form": link_form},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def related_link_delete(request, pk, link_id):
    parent_form = _form_for_manage(request, pk)
    link = get_object_or_404(SupplementaryFormLink, pk=link_id, parent_form=parent_form)
    link.delete()
    messages.success(request, _("Related link removed."))
    return redirect("manage:related_link_list", pk=pk)


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def form_soft_delete(request, pk):
    """Delete a form (soft delete): unpublish and hide from public and normal lists; restorable."""
    form_instance = get_object_or_404(
        forms_queryset_for_user(request.user, visibility="all", request=request).select_related("entity"),
        pk=pk,
    )
    if form_instance.deleted_at:
        messages.info(request, _("This form is already deleted."))
        return redirect("manage:form_detail", pk=pk)
    if (request.POST.get("confirm") or "").strip().lower() != "confirm":
        messages.error(request, _("Type “confirm” to delete this form."))
        return redirect("manage:form_detail", pk=pk)
    now = timezone.now()
    Form.objects.filter(pk=form_instance.pk).update(
        deleted_at=now,
        is_published=False,
        updated_at=now,
    )
    messages.success(
        request,
        _("The form “%(title)s” was moved to Deleted forms.") % {"title": form_instance.title},
    )
    return redirect(f"{reverse('manage:dashboard')}?undo={oid_encode(form_instance.pk)}")


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def form_restore(request, pk):
    """Bring back a deleted form (organization admins with forms-write, and super admins)."""
    form_instance = get_object_or_404(
        forms_queryset_for_user(request.user, visibility="all", request=request).select_related("entity"),
        pk=pk,
    )
    if not form_instance.deleted_at:
        messages.info(request, _("This form is not deleted."))
        return redirect("manage:form_detail", pk=pk)
    now = timezone.now()
    Form.objects.filter(pk=form_instance.pk).update(deleted_at=None, updated_at=now)
    messages.success(request, _("The form “%(title)s” was restored.") % {"title": form_instance.title})
    next_url = (request.POST.get("next") or "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("manage:form_detail", pk=pk)


@studio_capability_required(MANAGE_FORMS_WRITE)
def logo_list(request, pk):
    form_instance = _form_for_manage(request, pk)
    logos = list(form_instance.logos.order_by("header_slot", "id"))
    return render(
        request,
        "magicforms/manage/logo_list.html",
        {
            "form_obj": form_instance,
            "logos": logos,
            "can_add_logo": len(logos) < FormLogo.MAX_PER_FORM,
        },
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def logo_add(request, pk):
    form_instance = _form_for_manage(request, pk)
    if form_instance.logos.count() >= FormLogo.MAX_PER_FORM:
        messages.error(request, _("This form already has the maximum of three logos."))
        return redirect("manage:logo_list", pk=form_instance.pk)
    if request.method == "POST":
        f = StaffLogoForm(request.POST, request.FILES, form_instance=form_instance)
        if f.is_valid():
            logo = f.save(commit=False)
            logo.form = form_instance
            logo.save()
            messages.success(request, _("Logo added."))
            return redirect("manage:logo_list", pk=form_instance.pk)
    else:
        f = StaffLogoForm(
            form_instance=form_instance,
            initial={"header_slot": form_instance.next_free_logo_header_slot()},
        )
    return render(
        request,
        "magicforms/manage/logo_form.html",
        {"form_obj": form_instance, "form": f, "editing_logo": False},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def logo_edit(request, pk, logo_id):
    form_instance = _form_for_manage(request, pk)
    logo = get_object_or_404(FormLogo, pk=logo_id, form=form_instance)
    if request.method == "POST":
        f = StaffLogoForm(
            request.POST,
            request.FILES,
            instance=logo,
            form_instance=form_instance,
        )
        if f.is_valid():
            f.save()
            messages.success(request, _("Logo updated."))
            return redirect("manage:logo_list", pk=form_instance.pk)
    else:
        f = StaffLogoForm(instance=logo, form_instance=form_instance)
    return render(
        request,
        "magicforms/manage/logo_form.html",
        {"form_obj": form_instance, "form": f, "editing_logo": True},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def logo_delete(request, pk, logo_id):
    form_instance = _form_for_manage(request, pk)
    logo = get_object_or_404(FormLogo, pk=logo_id, form=form_instance)
    logo.delete()
    messages.success(request, _("Logo removed."))
    return redirect("manage:logo_list", pk=form_instance.pk)


@studio_capability_required(MANAGE_FORMS_WRITE)
def form_edit(request, pk):
    form_instance = _form_for_manage(request, pk)
    if request.method == "POST":
        f = StaffMetaForm(
            request.POST,
            request.FILES,
            instance=form_instance,
            staff_user=request.user,
            request=request,
        )
        if f.is_valid():
            obj = f.save()
            if _maybe_unpublish(obj):
                messages.warning(
                    request,
                    _(
                        "Publishing turned off until you add at least one field and one workflow step."
                    ),
                )
            else:
                messages.success(request, _("Saved."))
            return redirect("manage:form_detail", pk=obj.pk)
    else:
        f = StaffMetaForm(instance=form_instance, staff_user=request.user, request=request)
    routing_mode_locked = form_instance.submissions.filter(
        workflow_state=FormSubmission.WorkflowState.IN_PROGRESS
    ).exists()
    return render(
        request,
        "magicforms/manage/form_edit.html",
        {"form_obj": form_instance, "form": f, "routing_mode_locked": routing_mode_locked},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def form_intro_edit(request, pk):
    form_instance = _form_for_manage(request, pk)
    if request.method == "POST":
        f = StaffIntroPageForm(
            request.POST,
            request.FILES,
            instance=form_instance,
        )
        if f.is_valid():
            f.save()
            messages.success(request, _("Announcement page saved."))
            return redirect("manage:form_detail", pk=form_instance.pk)
    else:
        f = StaffIntroPageForm(instance=form_instance)
    intro_slides = list(form_instance.get_ordered_intro_slides())
    public_intro_url = form_instance.build_public_form_absolute_url(request)
    return render(
        request,
        "magicforms/manage/form_intro_edit.html",
        {
            "form_obj": form_instance,
            "form": f,
            "public_intro_url": public_intro_url,
            "intro_slides": intro_slides,
            "can_add_intro_slide": len(intro_slides) < FormIntroSlide.MAX_PER_FORM,
            "intro_slide_max": FormIntroSlide.MAX_PER_FORM,
            "slide_form": StaffIntroSlideForm(),
        },
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def intro_slide_add(request, pk):
    form_instance = _form_for_manage(request, pk)
    if form_instance.intro_slides.count() >= FormIntroSlide.MAX_PER_FORM:
        messages.error(
            request,
            _("This form already has the maximum number of slideshow images (%(max)s).")
            % {"max": FormIntroSlide.MAX_PER_FORM},
        )
        return redirect("manage:form_intro_edit", pk=form_instance.pk)
    f = StaffIntroSlideForm(request.POST, request.FILES)
    if f.is_valid():
        slide = f.save(commit=False)
        slide.form = form_instance
        agg = form_instance.intro_slides.aggregate(m=Max("sort_order"))
        slide.sort_order = (agg["m"] or 0) + 1
        slide.save()
        messages.success(request, _("Gallery image added."))
    else:
        messages.error(request, _("Could not add image. Check the file and try again."))
    return redirect("manage:form_intro_edit", pk=form_instance.pk)


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def intro_slide_delete(request, pk, slide_id):
    form_instance = _form_for_manage(request, pk)
    slide = get_object_or_404(FormIntroSlide, pk=slide_id, form=form_instance)
    slide.delete()
    messages.success(request, _("Gallery image removed."))
    return redirect("manage:form_intro_edit", pk=form_instance.pk)


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def intro_slide_reorder(request, pk):
    form_instance = _form_for_manage(request, pk)
    try:
        payload = json.loads(request.body.decode())
        ids = payload.get("order")
        if not isinstance(ids, list):
            return JsonResponse({"error": "order must be a list"}, status=400)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid JSON"}, status=400)

    with transaction.atomic():
        for index, sid in enumerate(ids):
            FormIntroSlide.objects.filter(pk=sid, form=form_instance).update(
                sort_order=index
            )
    return JsonResponse({"ok": True})


@studio_capability_required(MANAGE_FORMS_WRITE)
def form_intro_preview(request, pk):
    """Staff preview of the public information page."""
    visibility = "all" if request.user.is_superuser else "active"
    form_def = get_object_or_404(
        forms_queryset_for_user(request.user, visibility=visibility, request=request)
        .select_related("category", "entity")
        .prefetch_related("intro_slides"),
        pk=pk,
    )
    from .views import _render_form_intro

    return _render_form_intro(
        request,
        form_def,
        form_def.entity,
        studio_intro_preview=True,
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def form_print_template_download(request, pk):
    """Serve the primary print template (DOCX or PDF) for offline editing and re-upload."""
    form_instance = _form_for_manage(request, pk)
    pf = form_instance.print_template
    if not pf or not getattr(pf, "name", None):
        raise Http404(_("This form has no primary print template to download."))
    basename = os.path.basename(pf.name)
    content_type = mimetypes.guess_type(basename)[0]
    if not content_type:
        content_type = "application/octet-stream"
    try:
        fh = pf.open("rb")
    except FileNotFoundError as exc:
        raise Http404(_("Print template file is missing from storage.")) from exc
    return FileResponse(
        fh,
        as_attachment=True,
        filename=basename,
        content_type=content_type,
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def form_print_template_odt_download(request, pk):
    """Serve the optional ODT print template for offline editing."""
    form_instance = _form_for_manage(request, pk)
    pf = form_instance.print_template_odt
    if not pf or not getattr(pf, "name", None):
        raise Http404(_("This form has no ODT print template to download."))
    basename = os.path.basename(pf.name)
    content_type = mimetypes.guess_type(basename)[0]
    if not content_type:
        content_type = "application/vnd.oasis.opendocument.text"
    try:
        fh = pf.open("rb")
    except FileNotFoundError as exc:
        raise Http404(_("ODT template file is missing from storage.")) from exc
    return FileResponse(
        fh,
        as_attachment=True,
        filename=basename,
        content_type=content_type,
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def field_list(request, pk):
    form_instance = _form_for_manage(request, pk)
    fields = list(form_instance.get_ordered_fields())
    return render(
        request,
        "magicforms/manage/field_list.html",
        {"form_obj": form_instance, "fields": fields},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def field_reorder(request, pk):
    form_instance = _form_for_manage(request, pk)
    try:
        payload = json.loads(request.body.decode())
        ids = payload.get("order")
        if not isinstance(ids, list):
            return JsonResponse({"error": "order must be a list"}, status=400)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid JSON"}, status=400)

    with transaction.atomic():
        for index, fid in enumerate(ids):
            FormField.objects.filter(pk=fid, form=form_instance).update(order=index)

    if _maybe_unpublish(form_instance):
        pass
    return JsonResponse({"ok": True})


@studio_capability_required(MANAGE_FORMS_WRITE)
def field_add(request, pk):
    form_instance = _form_for_manage(request, pk)
    mx = FormField.objects.filter(form=form_instance).aggregate(m=Max("order"))["m"]
    next_order = (mx if mx is not None else -1) + 1
    if request.method == "POST":
        f = StaffFieldForm(request.POST, form_instance=form_instance)
        if f.is_valid():
            ff = f.save(commit=False)
            ff.form = form_instance
            ff.order = next_order
            ff.save()
            if _maybe_unpublish(form_instance):
                messages.warning(request, _("Publishing turned off until workflow has steps."))
            messages.success(request, _("Field added."))
            return redirect("manage:field_list", pk=form_instance.pk)
    else:
        f = StaffFieldForm(form_instance=form_instance)
    return render(
        request,
        "magicforms/manage/field_form.html",
        {"form_obj": form_instance, "form": f, "mode": "add"},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def field_edit(request, pk, field_id):
    form_instance = _form_for_manage(request, pk)
    field = get_object_or_404(FormField, pk=field_id, form=form_instance)
    if request.method == "POST":
        f = StaffFieldForm(request.POST, instance=field, form_instance=form_instance)
        if f.is_valid():
            f.save()
            messages.success(request, _("Field updated."))
            return redirect("manage:field_list", pk=form_instance.pk)
    else:
        f = StaffFieldForm(instance=field, form_instance=form_instance)
    return render(
        request,
        "magicforms/manage/field_form.html",
        {"form_obj": form_instance, "form": f, "mode": "edit", "field_obj": field},
    )


def _unique_form_field_name(form_instance, base_name: str) -> str:
    """Return a ``name`` slug unique for this form (used when duplicating a field)."""
    from .slug_utils import unique_form_field_name

    root = (base_name or "field").strip()[:80]
    n = 0
    while n < 500:
        suffix = "-copy" if n == 0 else f"-copy-{n + 1}"
        stem_len = max(0, 80 - len(suffix))
        candidate = (root[:stem_len] + suffix)[:80]
        if not FormField.objects.filter(form=form_instance, name=candidate).exists():
            return candidate
        n += 1
    return unique_form_field_name(root, form_instance)


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def field_duplicate(request, pk, field_id):
    form_instance = _form_for_manage(request, pk)
    src = get_object_or_404(FormField, pk=field_id, form=form_instance)
    new_name = _unique_form_field_name(form_instance, src.name)
    new_label = (src.label + _(" (copy)"))[:255]
    with transaction.atomic():
        old_order = src.order
        FormField.objects.filter(form=form_instance, order__gt=old_order).update(order=F("order") + 1)
        new_field = FormField(
            form=form_instance,
            order=old_order + 1,
            name=new_name,
            label=new_label,
            field_type=src.field_type,
            mapping_key=src.mapping_key,
            hint=src.hint,
            help_text=src.help_text,
            placeholder=src.placeholder,
            required=src.required,
            choices_text=src.choices_text,
            options_layout=src.options_layout,
            inline=src.inline,
            visibility_control_field_id=src.visibility_control_field_id,
            visibility_show_when_values=src.visibility_show_when_values,
            section_id=src.section_id,
            validation_min_length=src.validation_min_length,
            validation_max_length=src.validation_max_length,
            validation_must_contain=src.validation_must_contain,
            validation_must_not_contain=src.validation_must_not_contain,
            validation_must_equal=src.validation_must_equal,
            validation_regex=src.validation_regex,
            validation_integer_only=src.validation_integer_only,
            validation_decimal_min=src.validation_decimal_min,
            validation_decimal_max=src.validation_decimal_max,
            validation_date_after=src.validation_date_after,
            validation_date_before=src.validation_date_before,
            validation_unique_value=src.validation_unique_value,
        )
        new_field.save()
    _maybe_unpublish(form_instance)
    messages.success(request, _("Field duplicated. You can adjust the internal name and label if needed."))
    return redirect("manage:field_edit", pk=form_instance.pk, field_id=new_field.pk)


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def field_delete(request, pk, field_id):
    form_instance = _form_for_manage(request, pk)
    field = get_object_or_404(FormField, pk=field_id, form=form_instance)
    field.delete()
    _maybe_unpublish(form_instance)
    messages.success(request, _("Field removed."))
    return redirect("manage:field_list", pk=form_instance.pk)


@studio_capability_required(MANAGE_FORMS_WRITE)
def workflow_list(request, pk):
    form_instance = _form_for_manage(request, pk)
    steps = list(form_instance.get_ordered_workflow_steps())
    return render(
        request,
        "magicforms/manage/workflow_list.html",
        {"form_obj": form_instance, "steps": steps},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def workflow_reorder(request, pk):
    form_instance = _form_for_manage(request, pk)
    try:
        payload = json.loads(request.body.decode())
        ids = payload.get("order")
        if not isinstance(ids, list):
            return JsonResponse({"error": "order must be a list"}, status=400)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid JSON"}, status=400)

    with transaction.atomic():
        for index, sid in enumerate(ids):
            WorkflowStep.objects.filter(pk=sid, form=form_instance).update(order=index)

    _maybe_unpublish(form_instance)
    return JsonResponse({"ok": True})


@studio_capability_required(MANAGE_FORMS_WRITE)
def workflow_add(request, pk):
    form_instance = _form_for_manage(request, pk)
    mx = WorkflowStep.objects.filter(form=form_instance).aggregate(m=Max("order"))["m"]
    next_order = (mx if mx is not None else -1) + 1
    if request.method == "POST":
        f = StaffWorkflowForm(request.POST, form_instance=form_instance)
        if f.is_valid():
            step = f.save(commit=False)
            step.form = form_instance
            step.order = next_order
            step.save()
            f.save_m2m()
            if _maybe_unpublish(form_instance):
                messages.warning(request, _("Publishing turned off until you add at least one field."))
            messages.success(request, _("Step added."))
            return redirect("manage:workflow_list", pk=form_instance.pk)
    else:
        f = StaffWorkflowForm(form_instance=form_instance)
    return render(
        request,
        "magicforms/manage/workflow_form.html",
        {"form_obj": form_instance, "form": f, "mode": "add"},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def workflow_edit(request, pk, step_id):
    form_instance = _form_for_manage(request, pk)
    step = get_object_or_404(WorkflowStep, pk=step_id, form=form_instance)
    if request.method == "POST":
        f = StaffWorkflowForm(request.POST, instance=step, form_instance=form_instance)
        if f.is_valid():
            f.save()
            messages.success(request, _("Step updated."))
            return redirect("manage:workflow_list", pk=form_instance.pk)
    else:
        f = StaffWorkflowForm(instance=step, form_instance=form_instance)
    return render(
        request,
        "magicforms/manage/workflow_form.html",
        {"form_obj": form_instance, "form": f, "mode": "edit", "step_obj": step},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def workflow_delete(request, pk, step_id):
    form_instance = _form_for_manage(request, pk)
    step = get_object_or_404(WorkflowStep, pk=step_id, form=form_instance)
    try:
        step.delete()
    except ProtectedError:
        messages.error(
            request,
            _(
                "Cannot delete this step while submissions reference it. Move submissions to another step first."
            ),
        )
        return redirect("manage:workflow_list", pk=form_instance.pk)
    _maybe_unpublish(form_instance)
    messages.success(request, _("Step removed."))
    return redirect("manage:workflow_list", pk=form_instance.pk)


@studio_capability_required(MANAGE_FORMS_WRITE)
def section_list(request, pk):
    form_instance = _form_for_manage(request, pk)
    sections = list(form_instance.get_ordered_sections())
    return render(
        request,
        "magicforms/manage/section_list.html",
        {"form_obj": form_instance, "sections": sections},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def section_reorder(request, pk):
    form_instance = _form_for_manage(request, pk)
    try:
        payload = json.loads(request.body.decode())
        ids = payload.get("order")
        if not isinstance(ids, list):
            return JsonResponse({"error": "order must be a list"}, status=400)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid JSON"}, status=400)

    with transaction.atomic():
        for index, sid in enumerate(ids):
            FormSection.objects.filter(pk=sid, form=form_instance).update(order=index)

    return JsonResponse({"ok": True})


@studio_capability_required(MANAGE_FORMS_WRITE)
def section_add(request, pk):
    form_instance = _form_for_manage(request, pk)
    mx = FormSection.objects.filter(form=form_instance).aggregate(m=Max("order"))["m"]
    next_order = (mx if mx is not None else -1) + 1
    if request.method == "POST":
        f = StaffSectionForm(request.POST)
        if f.is_valid():
            sec = f.save(commit=False)
            sec.form = form_instance
            sec.order = next_order
            sec.save()
            messages.success(request, _("Section added."))
            return redirect("manage:section_list", pk=form_instance.pk)
    else:
        f = StaffSectionForm()
    return render(
        request,
        "magicforms/manage/section_form.html",
        {"form_obj": form_instance, "form": f, "mode": "add"},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
def section_edit(request, pk, section_id):
    form_instance = _form_for_manage(request, pk)
    sec = get_object_or_404(FormSection, pk=section_id, form=form_instance)
    if request.method == "POST":
        f = StaffSectionForm(request.POST, instance=sec)
        if f.is_valid():
            f.save()
            messages.success(request, _("Section updated."))
            return redirect("manage:section_list", pk=form_instance.pk)
    else:
        f = StaffSectionForm(instance=sec)
    return render(
        request,
        "magicforms/manage/section_form.html",
        {"form_obj": form_instance, "form": f, "mode": "edit", "section_obj": sec},
    )


@studio_capability_required(MANAGE_FORMS_WRITE)
@require_POST
def section_delete(request, pk, section_id):
    form_instance = _form_for_manage(request, pk)
    sec = get_object_or_404(FormSection, pk=section_id, form=form_instance)
    sec.delete()
    messages.success(request, _("Section removed. Fields in it were set to no section."))
    return redirect("manage:section_list", pk=form_instance.pk)


@studio_access_required
def submission_document_view(request, pk, submission_id):
    """Full-page embedded merged PDF (DOCX/ODT templates require LibreOffice for conversion)."""
    form_instance = _form_for_manage(request, pk)
    submission = get_object_or_404(
        FormSubmission.objects.select_related("submitted_by")
        .prefetch_related(
            "values__field",
            Prefetch(
                "events",
                queryset=SubmissionEvent.objects.select_related("step", "created_by").order_by(
                    "created_at",
                ),
            ),
            Prefetch(
                "submitted_by__signatures",
                queryset=UserSignature.objects.order_by("sort_order", "id"),
            ),
        ),
        pk=submission_id,
        form=form_instance,
    )
    _require_submission_portal_or_staff(request, submission)
    caps = print_template_merge_capabilities(form_instance)
    can_view_pdf = bool(caps["merged_pdf_available"])
    pdf_inline_path = ""
    if can_view_pdf:
        pdf_inline_path = (
            reverse(
                "manage:submission_merge_document",
                kwargs={"pk": pk, "submission_id": submission_id, "fmt": "pdf"},
            )
            + "?inline=1"
        )
    return render(
        request,
        "magicforms/manage/submission_document_view.html",
        {
            "form_obj": form_instance,
            "submission": submission,
            "can_view_pdf": can_view_pdf,
            "pdf_inline_path": pdf_inline_path,
            "show_docx_download": caps["show_docx_download"],
            "show_odt_download": caps["show_odt_download"],
            "print_has_odt_secondary": caps["has_odt_secondary"],
        },
    )


@studio_access_required
@xframe_options_sameorigin
def submission_merge_document(request, pk, submission_id, fmt):
    """Download or inline-serve merged print template (DOCX, ODT, PDF). Pass ``?inline=1`` for browser embed."""
    fmt = (fmt or "").lower()
    if fmt not in ("docx", "pdf", "odt"):
        raise Http404("Unsupported format.")
    inline = request.GET.get("inline") in ("1", "true", "yes")
    form_instance = _form_for_manage(request, pk)
    submission = get_object_or_404(
        FormSubmission.objects.select_related("submitted_by")
        .prefetch_related(
            "values__field",
            Prefetch(
                "events",
                queryset=SubmissionEvent.objects.select_related("step", "created_by").order_by(
                    "created_at",
                ),
            ),
            Prefetch(
                "submitted_by__signatures",
                queryset=UserSignature.objects.order_by("sort_order", "id"),
            ),
        ),
        pk=submission_id,
        form=form_instance,
    )
    _require_submission_portal_or_staff(request, submission)
    try:
        data, filename, content_type = render_submission_document(submission, fmt)
    except PrintMergeError as exc:
        if inline:
            return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
        messages.error(request, str(exc))
        return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)
    from .print_merge import merged_document_http_response

    return merged_document_http_response(
        data, filename, content_type, inline=inline
    )


@studio_access_required
@xframe_options_sameorigin
def submission_attachment_pdf(request, pk, submission_id, attachment_id):
    """Convert a submission attachment (DOC, DOCX, or ODT) to PDF for in-browser preview."""
    inline = request.GET.get("inline") in ("1", "true", "yes")
    form_instance = _form_for_manage(request, pk)
    submission = get_object_or_404(
        FormSubmission.objects.select_related("form__entity"),
        pk=submission_id,
        form=form_instance,
    )
    _require_submission_portal_or_staff(request, submission)
    att = get_object_or_404(SubmissionAttachment, pk=attachment_id, submission=submission)
    ext = attachment_source_ext_for_pdf(att)
    if not ext or not docx_to_pdf_available():
        msg = _("PDF preview is not available for this file.")
        if inline:
            return HttpResponse(str(msg), status=400, content_type="text/plain; charset=utf-8")
        messages.error(request, msg)
        return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)
    try:
        att.file.open("rb")
        try:
            raw = att.file.read()
        finally:
            att.file.close()
        pdf_bytes = libreoffice_bytes_to_pdf(raw, f"attachment_{att.pk}", ext)
        pdf_bytes = stamp_entity_logo_on_pdf(pdf_bytes, submission.form.entity)
    except PrintMergeError as exc:
        if inline:
            return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
        messages.error(request, str(exc))
        return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)
    stem = get_valid_filename(os.path.splitext(os.path.basename(att.file.name))[0])[:120] or f"attachment_{att.pk}"
    return FileResponse(
        BytesIO(pdf_bytes),
        as_attachment=not inline,
        filename=f"{stem}.pdf",
        content_type="application/pdf",
    )


@studio_capability_required(*read_or_write(VIEW_RESPONSES))
def submission_list(request, pk):
    form_instance = _form_for_manage(request, pk)
    subs_qs = (
        form_instance.submissions.select_related("current_step")
        .prefetch_related("current_step__assigned_users")
        .order_by("-submitted_at")
    )
    subs_page, per_page = paginate(request, subs_qs)
    page_subs = list(subs_page.object_list)
    # Fixed-step forms only; a dynamic-routing form's quick action (if any) goes through
    # ``current_holder``, not a fixed step's assignees, and leftover WorkflowStep rows from
    # before it was switched no longer mean anything.
    form_has_workflow_steps = (
        form_instance.routing_mode == Form.RoutingMode.FIXED_STEPS and form_instance.workflow_steps.exists()
    )
    for _s in page_subs:
        _s.list_workflow_quick_enabled = form_has_workflow_steps and user_may_act_on_submission_workflow(
            request.user, _s
        )
    return render(
        request,
        "magicforms/manage/submission_list.html",
        {
            "form_obj": form_instance,
            "form_has_workflow_steps": form_has_workflow_steps,
            "submissions": subs_page,
            "per_page": per_page,
            "per_page_choices": STUDIO_PER_PAGE_CHOICES,
            "workflow_undo_window_minutes": UNDO_APPROVE_MINUTES,
        },
    )


_APPROVER_SIGNATURE_PLACEHOLDERS = ("approver_signature_primary", "approver_signatures")


def _docx_template_maps_approver_signature(form_instance) -> bool:
    """True when the form's DOCX print template embeds the approver's stored signature itself."""
    import re as _re
    import zipfile

    tpl = form_instance.print_template
    if not tpl or not str(tpl.name or "").lower().endswith(".docx"):
        return False
    try:
        with tpl.open("rb") as fh, zipfile.ZipFile(fh) as zf:
            for name in zf.namelist():
                if not (name.startswith("word/") and name.endswith(".xml")):
                    continue
                text = _re.sub(r"<[^>]+>", "", zf.read(name).decode("utf-8", "ignore"))
                if any(ph in text for ph in _APPROVER_SIGNATURE_PLACEHOLDERS):
                    return True
    except (OSError, ValueError, zipfile.BadZipFile):
        return False
    return False


def _studio_saved_signature(request):
    """The requester's primary stored signature (first by sort order), or ``None``."""
    u = request.user
    if not getattr(u, "is_authenticated", False):
        return None
    return u.signatures.order_by("sort_order", "id").first()


def _staff_may_sign_document(request, submission) -> bool:
    """
    Studio signing is tied to acting: only someone who can currently act on this submission (an
    assignee or active delegate on the current step for fixed-step forms; the dynamic-routing
    current holder or their delegate for dynamic forms) may add or remove signatures. Everyone
    else, superusers included, reads the document only.
    """
    return user_may_act_on_submission_workflow(request.user, submission)


def _studio_signature_submission(request, pk, submission_id):
    form_instance = _form_for_manage(request, pk)
    submission = get_object_or_404(FormSubmission.objects.select_related("form", "form__entity"), pk=submission_id, form=form_instance)
    _require_submission_portal_or_staff(request, submission)
    if not _staff_may_sign_document(request, submission):
        return None, JsonResponse(
            {"ok": False, "error": _("No action is required from you on this submission, so the document is read-only."), "locked": "noaction"},
            status=403,
        )
    return submission, None


@studio_access_required
@require_POST
def submission_signature_place(request, pk, submission_id):
    """Studio: stamp a drawn signature onto the merged PDF of a submission."""
    submission, denied = _studio_signature_submission(request, pk, submission_id)
    if denied:
        return denied
    return signature_place_response(request, submission, allow_saved=True, remember_drawing=True)


@studio_access_required
@require_POST
def submission_signature_remove(request, pk, submission_id, placement_id):
    submission, denied = _studio_signature_submission(request, pk, submission_id)
    if denied:
        return denied
    return signature_remove_response(request, submission, placement_id)


@studio_access_required
@never_cache
def submission_manage_detail(request, pk, submission_id):
    form_instance = _form_for_manage(request, pk)
    submission = get_object_or_404(
        FormSubmission.objects.select_related(
            "form", "current_step", "submitted_by", "current_holder"
        ).prefetch_related(
            "current_step__assigned_users",
            "values__field",
            "events__step",
            "events__created_by",
            "document_attachments",
            Prefetch(
                "thread_messages",
                queryset=SubmissionThreadMessage.objects.select_related("author").order_by("created_at"),
            ),
            Prefetch(
                "applicant_messages",
                queryset=SubmissionApplicantMessage.objects.select_related("author").order_by("created_at"),
            ),
        ),
        pk=submission_id,
        form=form_instance,
    )
    _require_submission_portal_or_staff(request, submission)
    _record_inbox_submission_detail_viewed(request, submission)
    values = sorted(submission.values.all(), key=lambda v: (v.field.order, v.field_id))
    events = list(submission.events.all())
    document_attachments = list(submission.document_attachments.all())
    thread_messages = list(submission.thread_messages.all())

    ensure_related_invitations(submission)
    related_instances = list(
        SupplementarySubmission.objects.filter(parent_submission_id=submission.pk)
        .select_related("link__child_form", "child_submission")
        .order_by("invited_at", "id")
    )

    applicant_email_form_bound: StaffSubmissionApplicantEmailForm | None = None
    skip_manage_post_redirect = False

    if request.method == "POST":
        if (request.POST.get("submission_private_sticky_save") or "").strip() == "1":
            raw = request.POST.get("private_sticky_body") or ""
            max_len = SubmissionPrivateStickyNote.MAX_BODY_LEN
            body = raw[:max_len]
            if not body.strip():
                SubmissionPrivateStickyNote.objects.filter(
                    submission=submission,
                    user=request.user,
                ).delete()
            else:
                SubmissionPrivateStickyNote.objects.update_or_create(
                    submission=submission,
                    user=request.user,
                    defaults={"body": body},
                )
            url = reverse("manage:submission_manage_detail", kwargs={"pk": pk, "submission_id": submission_id})
            return redirect(f"{url}?sn=1")

        if (request.POST.get("submission_user_tags_save") or "").strip() == "1":
            labels = SubmissionUserTag.parse_tag_input(request.POST.get("user_tags_input") or "")
            SubmissionUserTag.objects.filter(submission=submission, user=request.user).delete()
            if labels:
                SubmissionUserTag.objects.bulk_create(
                    [SubmissionUserTag(submission=submission, user=request.user, label=lb) for lb in labels]
                )
            messages.success(request, _("Your tags were updated."))
            return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)

        if (request.POST.get("submission_user_tag_remove") or "").strip() == "1":
            rid = (request.POST.get("user_tag_id") or "").strip()
            if rid.isdigit():
                n, _deleted = SubmissionUserTag.objects.filter(
                    pk=int(rid),
                    submission=submission,
                    user=request.user,
                ).delete()
                if n:
                    messages.success(request, _("Tag removed."))
            return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)

        if (request.POST.get("submission_thread_post") or "").strip() == "1":
            body = (request.POST.get("thread_message_body") or "").strip()
            max_len = SubmissionThreadMessage.MAX_BODY_LEN
            if not body:
                messages.error(request, _("Enter a message before posting."))
            elif len(body) > max_len:
                messages.error(
                    request,
                    _("Message is too long (%(n)d characters maximum).") % {"n": max_len},
                )
            else:
                SubmissionThreadMessage.objects.create(
                    submission=submission,
                    author=request.user,
                    body=body[:max_len],
                )
                messages.success(request, _("Message posted."))
                _touch_submission_thread_last_read(request, submission)
            return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)

        if (request.POST.get("applicant_chat_post") or "").strip() == "1":
            from .notification_emails import dispatch_applicant_chat_email

            body = (request.POST.get("applicant_chat_body") or "").strip()
            max_len = SubmissionApplicantMessage.MAX_BODY_LEN
            if not body:
                messages.error(request, _("Enter a message before sending."))
            elif len(body) > max_len:
                messages.error(
                    request,
                    _("Message is too long (%(n)d characters maximum).") % {"n": max_len},
                )
            else:
                chat_msg = SubmissionApplicantMessage.objects.create(
                    submission=submission,
                    author=request.user,
                    is_from_applicant=False,
                    body=body[:max_len],
                )
                dispatch_applicant_chat_email(submission, chat_msg, request=request)
                messages.success(
                    request,
                    _("Message sent to the applicant. They were notified by email."),
                )
            return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)

        att_action = (request.POST.get("submission_attachment_action") or "").strip()
        if att_action == "add":
            att_form = StaffSubmissionAttachmentForm(
                request.POST,
                request.FILES,
                submission=submission,
            )
            if att_form.is_valid():
                att = att_form.save(commit=False)
                att.submission = submission
                att.uploaded_by = request.user
                att.save()
                fname = os.path.basename(att.file.name) if att.file else ""
                msg = f"Document added (manage): {fname}"
                if att.title:
                    msg = f"{msg} — {att.title}"
                SubmissionEvent.objects.create(
                    submission=submission,
                    kind=SubmissionEvent.Kind.ATTACHMENT_ADDED,
                    step=submission.current_step if submission.current_step_id else None,
                    message=msg[:1000],
                    created_by=request.user,
                )
                messages.success(request, _("Attachment uploaded."))
            else:
                for errs in att_form.errors.values():
                    for err in errs:
                        messages.error(request, str(err))
            return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)
        if att_action == "delete":
            aid = (request.POST.get("attachment_id") or "").strip()
            if aid.isdigit():
                att = submission.document_attachments.filter(pk=int(aid)).first()
                if att and attachment_may_delete_on_manage(request.user, submission, att):
                    fname = os.path.basename(att.file.name) if att.file else ""
                    att.delete()
                    SubmissionEvent.objects.create(
                        submission=submission,
                        kind=SubmissionEvent.Kind.NOTE,
                        step=submission.current_step if submission.current_step_id else None,
                        message=_("Attachment removed (manage): %(name)s") % {"name": fname or str(aid)},
                        created_by=request.user,
                    )
                    messages.success(request, _("Attachment removed."))
                elif att:
                    messages.error(
                        request,
                        _("You can only remove attachments you uploaded. Respondent files are removed from the public track page."),
                    )
                else:
                    messages.error(request, _("Attachment not found."))
            return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)

        if (request.POST.get("submission_applicant_email_send") or "").strip() == "1":
            from .entity_email import entity_email_notifications_ready
            from .submission_applicant_email import send_applicant_email

            entity = form_instance.entity
            mail_ok, mail_block = entity_email_notifications_ready(entity)
            if not mail_ok:
                messages.error(request, mail_block)
                return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)

            mail_form = StaffSubmissionApplicantEmailForm(
                request.POST,
                submission=submission,
            )
            if mail_form.is_valid():
                to_addr = mail_form.cleaned_data["to_email"]
                subj = mail_form.cleaned_data["subject"]
                body = mail_form.cleaned_data["message"]
                reply_to = (request.user.email or "").strip() or None
                try:
                    send_applicant_email(
                        submission,
                        to_email=to_addr,
                        subject=subj,
                        body=body,
                        reply_to=reply_to,
                    )
                except Exception as exc:
                    detail = str(exc).strip()
                    messages.error(
                        request,
                        _(
                            "Could not send the email. Check organization email settings (SMTP host, port, TLS/SSL, credentials) and try again."
                        )
                        + (f" ({detail})" if detail else ""),
                    )
                else:
                    SubmissionEvent.objects.create(
                        submission=submission,
                        kind=SubmissionEvent.Kind.NOTE,
                        step=submission.current_step if submission.current_step_id else None,
                        message=_("Email sent to applicant (%(addr)s): %(subject)s")
                        % {"addr": to_addr, "subject": subj[:120]},
                        created_by=request.user,
                    )
                    messages.success(
                        request,
                        _("Email sent to %(addr)s.") % {"addr": to_addr},
                    )
            else:
                for errs in mail_form.errors.values():
                    for err in errs:
                        messages.error(request, str(err))
                applicant_email_form_bound = mail_form
                skip_manage_post_redirect = True

        forward_action = (request.POST.get("submission_forward") or "").strip()
        if forward_action == "1":
            if not form_instance.allow_submission_forward:
                messages.error(request, _("Forwarding is not enabled for this form."))
            else:
                fwd_form = StaffSubmissionForwardForm(
                    request.POST,
                    actor=request.user,
                    form_entity_id=form_instance.entity_id,
                )
                if fwd_form.is_valid():
                    target = fwd_form.cleaned_data["target_user"]
                    note = (fwd_form.cleaned_data.get("note") or "").strip()
                    line = f"Forwarded to {target.get_username()}"
                    fn = (target.get_full_name() or "").strip()
                    if fn:
                        line += f" ({fn})"
                    if note:
                        line += f"\nNote: {note}"
                    SubmissionEvent.objects.create(
                        submission=submission,
                        kind=SubmissionEvent.Kind.FORWARDED,
                        step=submission.current_step if submission.current_step_id else None,
                        message=line[:1000],
                        created_by=request.user,
                    )
                    messages.success(request, _("Submission forwarded (timeline updated)."))
                else:
                    for errs in fwd_form.errors.values():
                        for err in errs:
                            messages.error(request, str(err))
            return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)

        if (request.POST.get("workflow_dynamic_route_submit") or "").strip() == "1" and (
            form_instance.uses_dynamic_routing
        ):
            route_form = StaffSubmissionRouteForm(
                request.POST,
                actor=request.user,
                form_entity_id=form_instance.entity_id,
                search_url=reverse("manage:user_search") + f"?form={oid_encode(form_instance.pk)}&scope=entity",
            )
            if route_form.is_valid():
                target = route_form.cleaned_data.get("target_user")
                ok, err, result = perform_dynamic_route_decision(
                    user=request.user,
                    submission=submission,
                    action=route_form.cleaned_data["action"],
                    target_user_id=target.pk if target else None,
                    stage_label=route_form.cleaned_data.get("stage_label", ""),
                    comment=route_form.cleaned_data.get("comment", ""),
                )
                if ok:
                    messages.success(request, (result or {}).get("message") or _("Done."))
                else:
                    messages.error(request, err or _("That action could not be completed."))
            else:
                for field_errs in route_form.errors.values():
                    for err in field_errs:
                        messages.error(request, str(err))
            return _submission_manage_post_redirect(request, pk, submission_id)

        if (request.POST.get("workflow_undo_last_approve") or "").strip() == "1":
            raw_eid = (request.POST.get("workflow_undo_event_id") or "").strip()
            ev_check = last_undoable_approve_event(request.user, submission)
            if raw_eid.isdigit() and ev_check and int(raw_eid) != ev_check.pk:
                messages.error(request, _("This page is out of date. Refresh and try again."))
                return _submission_manage_post_redirect(request, pk, submission_id)
            ok, err = perform_undo_last_approve(
                user=request.user,
                form_instance=form_instance,
                submission_id=submission.pk,
            )
            if ok:
                messages.success(request, _("Approval undone. The timeline records this change."))
            else:
                messages.error(request, err)
            return _submission_manage_post_redirect(request, pk, submission_id)

        decision = (request.POST.get("workflow_decision") or "").strip()
        if decision in ("approve", "reject"):
            has_steps = form_instance.workflow_steps.exists()
            if not has_steps:
                messages.error(request, _("This form has no workflow steps."))
                return _submission_manage_post_redirect(request, pk, submission_id)
            if not form_supports_workflow_decisions(form_instance):
                messages.error(
                    request,
                    _("Dynamic routing is being set up for this form; workflow actions aren't available yet."),
                )
                return _submission_manage_post_redirect(request, pk, submission_id)
            comment_raw = (request.POST.get("workflow_decision_comment") or "").strip()
            comment = comment_raw[:800]
            if decision == "reject" and not comment:
                messages.error(
                    request,
                    _("Enter a reason for rejection before submitting."),
                )
                return _submission_manage_post_redirect(request, pk, submission_id)

            anchor_raw = (request.POST.get("workflow_action_anchor") or "").strip()
            workflow_anchor: int | None
            if "workflow_action_anchor" not in request.POST:
                workflow_anchor = None
            else:
                try:
                    workflow_anchor = int(anchor_raw) if anchor_raw != "" else 0
                except ValueError:
                    messages.error(
                        request,
                        _("Invalid workflow action. Refresh the page and try again."),
                    )
                    return _submission_manage_post_redirect(request, pk, submission_id)

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
                    workflow_block_error = _("This submission is not awaiting approval.")
                elif not fresh.current_step_id:
                    workflow_block_error = _(
                        "Assign a workflow step before using approve or reject.",
                    )
                elif not user_may_act_on_submission_workflow(request.user, fresh):
                    workflow_block_error = _(
                        "You are not an assignee on this step and do not have an active delegation to act here.",
                    )
                elif workflow_anchor is not None and workflow_anchor != int(fresh.current_step_id):
                    workflow_block_error = _(
                        "This submission was already updated—perhaps in another tab. Refresh the page.",
                    )
                else:
                    delegate_suffix = delegate_action_suffix(request.user, fresh)

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
                            created_by=request.user,
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
                                created_by=request.user,
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
                                created_by=request.user,
                            )
                            approve_outcome = ("advanced", str(next_step.label))
                        ensure_related_invitations(fresh)

            if workflow_block_error:
                messages.error(request, workflow_block_error)
                return _submission_manage_post_redirect(request, pk, submission_id)

            if decision == "reject":
                messages.success(request, _("Submission rejected; workflow stopped here."))
            elif approve_outcome == "completed":
                messages.success(
                    request,
                    _(
                        "Approved — workflow is complete. You can undo this approval for "
                        "%(minutes)d minutes using Undo approve."
                    )
                    % {"minutes": UNDO_APPROVE_MINUTES},
                )
            elif isinstance(approve_outcome, tuple):
                messages.success(
                    request,
                    _(
                        'Approved — now at "%(step)s". You can undo this approval for '
                        "%(minutes)d minutes using Undo approve."
                    )
                    % {"step": approve_outcome[1], "minutes": UNDO_APPROVE_MINUTES},
                )
            elif decision == "approve":
                messages.error(
                    request,
                    _("Approval did not complete. Refresh the page and try again."),
                )
                return _submission_manage_post_redirect(request, pk, submission_id)

            from .notification_emails import queue_after_submission_event

            latest_event = (
                SubmissionEvent.objects.filter(submission_id=submission.pk)
                .order_by("-pk")
                .first()
            )
            if latest_event is not None:
                queue_after_submission_event(
                    submission,
                    latest_event,
                    request=request,
                    workflow_decision=decision,
                    workflow_decision_comment=comment,
                    staff_user=request.user,
                )

            remember_pid = (request.POST.get("remember_signature_placement") or "").strip()
            if remember_pid:
                remember_signature_from_placement(request.user, submission, remember_pid)

            _set_workflow_action_flash(request, submission.pk)
            return _submission_manage_post_redirect(request, pk, submission_id)

        if (request.POST.get("workflow_decision") or "").strip() and decision not in ("approve", "reject"):
            messages.error(
                request,
                _("Unrecognized workflow action. Refresh the page and use Approve or Reject."),
            )
            return _submission_manage_post_redirect(request, pk, submission_id)

        if not skip_manage_post_redirect:
            return redirect("manage:submission_manage_detail", pk=pk, submission_id=submission_id)

    caps = print_template_merge_capabilities(form_instance)
    print_has_templates = bool(caps["has_merge_output"])
    print_has_odt_secondary = bool(caps["has_odt_secondary"])
    pl = str(caps["primary_name_lower"] or "")
    print_is_docx = bool(caps["has_print_template"]) and pl.endswith(".docx")
    print_is_pdf = bool(caps["has_print_template"]) and pl.endswith(".pdf")
    print_can_view_pdf = bool(caps["merged_pdf_available"])
    merged_pdf_inline_path = ""
    sign_urls = None
    sign_lock_reason = None
    sign_saved_signature_id = None
    sign_saved_signature_url = ""
    sign_template_maps_approver = False
    if print_can_view_pdf:
        sign_urls = {
            "place": reverse(
                "manage:submission_signature_place", kwargs={"pk": form_instance.pk, "submission_id": submission.pk}
            ),
            "remove_template": reverse(
                "manage:submission_signature_remove",
                kwargs={"pk": form_instance.pk, "submission_id": submission.pk, "placement_id": 0},
            ),
        }
        if not _staff_may_sign_document(request, submission):
            sign_lock_reason = "noaction"
        saved_sig = _studio_saved_signature(request)
        sign_saved_signature_id = saved_sig.pk if saved_sig else None
        sign_saved_signature_url = saved_sig.image.url if saved_sig else ""
        sign_template_maps_approver = _docx_template_maps_approver_signature(form_instance)
        if sign_lock_reason is None and sign_template_maps_approver and saved_sig is not None:
            sign_lock_reason = "template"
    if print_can_view_pdf:
        merged_pdf_inline_path = (
            reverse(
                "manage:submission_merge_document",
                kwargs={
                    "pk": form_instance.pk,
                    "submission_id": submission.pk,
                    "fmt": "pdf",
                },
            )
            + "?inline=1"
        )

    suppress_workflow_buttons = _consume_workflow_action_flash(request, submission.pk)
    routing_mode_supported = form_supports_workflow_decisions(form_instance)
    workflow_decision_enabled = (
        routing_mode_supported
        and form_instance.workflow_steps.exists()
        and submission.workflow_state == FormSubmission.WorkflowState.IN_PROGRESS
        and submission.current_step_id
        and user_may_act_on_submission_workflow(request.user, submission)
        and not suppress_workflow_buttons
    )

    dynamic_route_enabled = False
    route_form = None
    submission_current_holder_label = ""
    if form_instance.uses_dynamic_routing:
        if submission.current_holder_id:
            holder = submission.current_holder
            submission_current_holder_label = holder.get_full_name() or holder.get_username()
        dynamic_route_enabled = (
            submission.workflow_state == FormSubmission.WorkflowState.IN_PROGRESS
            and user_may_act_on_submission_workflow(request.user, submission)
            and not suppress_workflow_buttons
        )
        if dynamic_route_enabled:
            route_form = StaffSubmissionRouteForm(
                actor=request.user,
                form_entity_id=form_instance.entity_id,
                search_url=reverse("manage:user_search") + f"?form={oid_encode(form_instance.pk)}&scope=entity",
            )
    # True only when nothing above applies: not fixed-step-actionable, not dynamic-actionable,
    # but still in progress — e.g. a dynamic submission currently held by someone else.
    workflow_dynamic_routing_pending = (
        form_instance.uses_dynamic_routing
        and not dynamic_route_enabled
        and submission.workflow_state == FormSubmission.WorkflowState.IN_PROGRESS
    )

    attachment_form = StaffSubmissionAttachmentForm(submission=submission)

    submission_attachment_rows = []
    for doc in document_attachments:
        ext = attachment_source_ext_for_pdf(doc)
        lo = bool(ext and docx_to_pdf_available())
        att_pdf_inline_path = ""
        if lo:
            att_pdf_inline_path = (
                reverse(
                    "manage:submission_attachment_pdf",
                    kwargs={
                        "pk": form_instance.pk,
                        "submission_id": submission.pk,
                        "attachment_id": doc.pk,
                    },
                )
                + "?inline=1"
            )
        submission_attachment_rows.append(
            {
                "doc": doc,
                "may_delete": attachment_may_delete_on_manage(request.user, submission, doc),
                "pdf_inline_path": att_pdf_inline_path,
            }
        )

    from .entity_email import entity_email_notifications_ready
    from .notification_emails import (
        resolve_notification_recipient,
        staff_contact_email_defaults,
    )
    from .submission_applicant_email import (
        applicant_email_source_label,
        default_applicant_email,
    )

    applicant_email_allowed, applicant_email_block_reason = entity_email_notifications_ready(
        form_instance.entity
    )
    app_email, app_email_source, app_email_field_label = default_applicant_email(submission)
    if applicant_email_form_bound is not None:
        applicant_email_form = applicant_email_form_bound
    else:
        default_subject, default_body = staff_contact_email_defaults(
            submission,
            request=request,
            staff_user=request.user,
        )
        applicant_email_form = StaffSubmissionApplicantEmailForm(
            initial={
                "to_email": app_email,
                "subject": default_subject,
                "body": default_body,
            },
            submission=submission,
        )
    applicant_email_source_hint = applicant_email_source_label(
        app_email_source,
        field_label=app_email_field_label,
    )

    forward_form = None
    if form_instance.allow_submission_forward:
        forward_form = StaffSubmissionForwardForm(
            actor=request.user,
            form_entity_id=form_instance.entity_id,
        )

    acting_as_delegate = False
    if submission.current_step_id and user_may_act_on_submission_workflow(request.user, submission):
        assignee_pks = set(submission.current_step.assigned_users.values_list("pk", flat=True))
        acting_as_delegate = request.user.pk not in assignee_pks

    undo_ev = last_undoable_approve_event(request.user, submission)
    workflow_undo_visible = undo_ev is not None
    workflow_undo_event_pk = undo_ev.pk if undo_ev else None

    private_sticky_note = SubmissionPrivateStickyNote.objects.filter(
        submission_id=submission.pk,
        user_id=request.user.pk,
    ).first()

    submission_private_tags = list(
        SubmissionUserTag.objects.filter(submission_id=submission.pk, user_id=request.user.pk).order_by("label")
    )
    private_tags_textarea_value = ", ".join(t.label for t in submission_private_tags)

    if request.method == "GET":
        _touch_submission_thread_last_read(request, submission)

    return render(
        request,
        "magicforms/manage/submission_manage_detail.html",
        {
            "form_obj": form_instance,
            "submission": submission,
            "values": values,
            "events": events,
            "document_attachments": document_attachments,
            "thread_messages": thread_messages,
            "applicant_chat_messages": list(submission.applicant_messages.all()),
            "applicant_chat_recipient": resolve_notification_recipient(submission),
            "submission_attachment_rows": submission_attachment_rows,
            "attachment_form": attachment_form,
            "attachment_max": SubmissionAttachment.MAX_PER_SUBMISSION,
            "print_has_templates": print_has_templates,
            "print_has_odt_secondary": print_has_odt_secondary,
            "print_is_docx": print_is_docx,
            "print_can_view_pdf": print_can_view_pdf,
            "pdf_inline_path": merged_pdf_inline_path,
            "sign_urls": sign_urls,
            "sign_lock_reason": sign_lock_reason,
            "sign_saved_signature_id": sign_saved_signature_id,
            "sign_saved_signature_url": sign_saved_signature_url,
            "sign_template_maps_approver": sign_template_maps_approver,
            "signature_placements": _signature_placements_payload(submission) if print_can_view_pdf else [],
            "sign_i18n": _signature_sign_i18n(),
            "workflow_decision_enabled": workflow_decision_enabled,
            "workflow_dynamic_routing_pending": workflow_dynamic_routing_pending,
            "dynamic_route_enabled": dynamic_route_enabled,
            "route_form": route_form,
            "submission_current_holder_label": submission_current_holder_label,
            "acting_as_delegate": acting_as_delegate,
            "workflow_undo_visible": workflow_undo_visible,
            "workflow_undo_event_pk": workflow_undo_event_pk,
            "workflow_undo_window_minutes": UNDO_APPROVE_MINUTES,
            "forward_form": forward_form,
            "applicant_email_form": applicant_email_form,
            "applicant_email_source_hint": applicant_email_source_hint,
            "applicant_email_allowed": applicant_email_allowed,
            "applicant_email_block_reason": applicant_email_block_reason,
            "entity_obj_for_email": form_instance.entity,
            "related_instances": related_instances,
            "private_sticky_note": private_sticky_note,
            "private_sticky_saved_check": (request.GET.get("sn") or "").strip() == "1",
            "submission_private_tags": submission_private_tags,
            "private_tags_textarea_value": private_tags_textarea_value,
            "user_submission_task": _user_submission_task_for_manage(
                request.user, submission
            ),
        },
    )


@studio_access_required
@never_cache
@require_GET
def submission_thread_messages_poll(request, pk, submission_id):
    """JSON: thread messages with id greater than optional ``since`` (for live refresh on manage detail)."""
    form_instance = _form_for_manage(request, pk)
    submission = get_object_or_404(
        FormSubmission.objects.select_related("form"),
        pk=submission_id,
        form=form_instance,
    )
    _require_submission_portal_or_staff(request, submission)
    since_raw = (request.GET.get("since") or "0").strip()
    try:
        since_id = int(since_raw)
    except ValueError:
        since_id = 0
    rows = (
        SubmissionThreadMessage.objects.filter(submission_id=submission.pk, pk__gt=since_id)
        .select_related("author")
        .order_by("created_at")
    )
    out = []
    for msg in rows:
        author = msg.author
        fn = (author.get_full_name() or "").strip()
        out.append(
            {
                "id": msg.pk,
                "author_username": author.get_username(),
                "author_full_name": fn,
                "created_title": msg.created_at.isoformat(),
                "created_display": dj_template_date(msg.created_at, "M j, Y, P"),
                "body_html": str(dj_linebreaksbr(msg.body)),
            }
        )
    _touch_submission_thread_last_read(request, submission)
    return JsonResponse({"messages": out})


@studio_access_required
@never_cache
def submission_timeline(request, pk, submission_id):
    """Full-page submission timeline with optional sharing."""
    from .timeline_shares import (
        timeline_share_message_for_submission,
        timeline_shares_for_submission,
        user_may_manage_timeline_sharing,
    )

    form_instance = _form_for_manage(request, pk)
    submission = get_object_or_404(
        FormSubmission.objects.select_related("form", "form__entity", "current_step", "submitted_by"),
        pk=submission_id,
        form=form_instance,
    )
    _require_submission_timeline_access(request, submission)
    from .timeline_shares import record_timeline_share_viewed, timeline_share_for_user

    record_timeline_share_viewed(request.user, submission)
    my_timeline_share = timeline_share_for_user(request.user, submission)
    events = list(
        submission.events.select_related("step", "created_by").order_by("created_at")
    )
    can_manage_sharing = user_may_manage_timeline_sharing(request.user, submission, request)
    can_open_submission_manage = can_manage_sharing
    shared_with_users = (
        list(timeline_shares_for_submission(submission).order_by("user__username"))
        if can_manage_sharing
        else []
    )
    open_share_panel = (request.GET.get("open_share") or "").strip() == "1"
    return render(
        request,
        "magicforms/manage/submission_timeline.html",
        {
            "form_obj": form_instance,
            "submission": submission,
            "events": events,
            "can_manage_sharing": can_manage_sharing,
            "can_open_submission_manage": can_open_submission_manage,
            "shared_with_users": shared_with_users,
            "open_share_panel": open_share_panel,
            "timeline_share_message": timeline_share_message_for_submission(submission),
            "my_timeline_share": my_timeline_share,
            "can_dismiss_share": my_timeline_share is not None,
        },
    )


@studio_access_required
@never_cache
@require_POST
def submission_timeline_share(request, pk, submission_id):
    from .timeline_shares import set_submission_timeline_shares, user_may_manage_timeline_sharing

    form_instance = _form_for_manage(request, pk)
    submission = get_object_or_404(
        FormSubmission.objects.select_related("form"),
        pk=submission_id,
        form=form_instance,
    )
    if not user_may_manage_timeline_sharing(request.user, submission, request):
        messages.error(request, _("You cannot change timeline sharing for this submission."))
        return redirect("manage:submission_timeline", pk=pk, submission_id=submission_id)
    from .timeline_shares import parse_share_user_ids_from_post

    user_ids = parse_share_user_ids_from_post(request.POST)
    share_message = (request.POST.get("share_message") or "").strip()
    if not user_ids:
        messages.error(
            request,
            _("Choose at least one colleague to share with, then click Update sharing."),
        )
        return redirect(
            f"{reverse('manage:submission_timeline', kwargs={'pk': pk, 'submission_id': submission_id})}?open_share=1#mf-timeline-share"
        )
    try:
        set_submission_timeline_shares(
            request.user,
            submission,
            user_ids=user_ids,
            share_message=share_message,
        )
    except ValueError:
        messages.error(
            request,
            _(
                "Those colleagues could not be given access. "
                "Choose active members of this form’s organization."
            ),
        )
        return redirect(
            f"{reverse('manage:submission_timeline', kwargs={'pk': pk, 'submission_id': submission_id})}?open_share=1#mf-timeline-share"
        )
    n = len(user_ids)
    messages.success(
        request,
        _("Timeline shared with %(count)d colleague(s). They will see it on Home under Shared timelines.")
        % {"count": n},
    )
    return redirect(
        f"{reverse('manage:submission_timeline', kwargs={'pk': pk, 'submission_id': submission_id})}?open_share=1#mf-timeline-share"
    )


@studio_access_required
@never_cache
@require_POST
def submission_timeline_dismiss(request, pk, submission_id):
    """Recipient hides a shared timeline on Home and revokes share-only access."""
    from .timeline_shares import dismiss_timeline_share_for_user, timeline_share_for_user

    form_instance = _form_for_manage(request, pk)
    submission = get_object_or_404(
        FormSubmission.objects.select_related("form"),
        pk=submission_id,
        form=form_instance,
    )
    if timeline_share_for_user(request.user, submission) is None:
        raise Http404()
    if dismiss_timeline_share_for_user(request.user, submission):
        messages.success(request, _("Removed from your shared timelines list."))
    return redirect("manage:dashboard")


@studio_access_required
@never_cache
@require_GET
def submission_timeline_pdf(request, pk, submission_id):
    """Download submission timeline as PDF (same layout as studio timeline list)."""
    form_instance = _form_for_manage(request, pk)
    submission = get_object_or_404(
        FormSubmission.objects.select_related(
            "form",
            "form__entity",
            "current_step",
            "submitted_by",
        ),
        pk=submission_id,
        form=form_instance,
    )
    _require_submission_timeline_access(request, submission)
    title, summary, entries = build_submission_timeline_pdf_payload(submission)
    try:
        raw = export_timeline_pdf_bytes(
            title,
            entries,
            summary_lines=summary,
            entity=submission.form.entity,
        )
    except RuntimeError as exc:
        return HttpResponse(str(exc), status=503, content_type="text/plain; charset=utf-8")
    stem = get_valid_filename(f"timeline_{submission.reference_token}")[:120] or "timeline"
    return FileResponse(
        BytesIO(raw),
        as_attachment=True,
        filename=f"{stem}.pdf",
        content_type="application/pdf",
    )


@studio_capability_required(*read_or_write(MANAGE_DELEGATIONS), any_entity=True)
def delegation_list(request):
    delegations_qs = (
        delegations_queryset_for_user(request.user, request=request)
        .select_related("entity", "delegator", "delegate", "created_by")
        .order_by("-created_at")
    )
    delegations_page, per_page = paginate(request, delegations_qs)
    return render(
        request,
        "magicforms/manage/delegation_list.html",
        {
            "delegations": delegations_page,
            "per_page": per_page,
            "per_page_choices": STUDIO_PER_PAGE_CHOICES,
        },
    )


@studio_capability_required(MANAGE_DELEGATIONS_WRITE, any_entity=True)
def delegation_add(request):
    eids = effective_entity_ids(request.user, request)
    if eids is not None and not eids:
        messages.error(
            request,
            _(
                "Your account is not assigned to any organization. Ask a superuser to add you to an entity."
            ),
        )
        return redirect("manage:dashboard")
    if request.method == "POST":
        form = StaffWorkflowDelegationForm(request.POST, staff_user=request.user, request=request)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, _("Delegation saved."))
            return redirect("manage:delegation_list")
    else:
        form = StaffWorkflowDelegationForm(staff_user=request.user, request=request)
    return render(
        request,
        "magicforms/manage/delegation_form.html",
        {"form": form},
    )


@studio_capability_required(MANAGE_DELEGATIONS_WRITE, any_entity=True)
@require_POST
def delegation_revoke(request, delegation_id):
    row = get_object_or_404(delegations_queryset_for_user(request.user, request=request), pk=delegation_id)
    row.is_active = False
    row.save(update_fields=["is_active"])
    messages.success(request, _("Delegation revoked."))
    return redirect("manage:delegation_list")


@staff_studio_required
@superuser_required
def choose_organization(request):
    """Super admins pick the organization to work in before the studio opens (see SuperuserOrganizationScopeMiddleware)."""
    q = (request.GET.get("q") or "").strip()
    qs = Entity.objects.annotate(forms_count=Count("forms", distinct=True)).order_by("-is_active", "name")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q) | Q(public_site_title__icontains=q))
    nxt = (request.GET.get("next") or "").strip()
    if not nxt.startswith("/") or nxt.startswith("//") or nxt.startswith(reverse("manage:choose_organization")):
        nxt = reverse("manage:dashboard")
    return render(
        request,
        "magicforms/manage/choose_organization.html",
        {"entities": list(qs), "search_q": q, "next_url": nxt, "hide_studio_rail": True},
    )


@staff_studio_required
@superuser_required
@require_POST
def superuser_entity_scope(request):
    """Persist superadmin studio entity scope (session). Empty selection = all organizations; one org otherwise."""
    from .models import Entity

    raw = (request.POST.get("entity_id") or "").strip()
    if raw.isdigit():
        eid = int(raw)
        if Entity.objects.filter(pk=eid).exists():
            request.session[MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY] = eid
            ent = Entity.objects.get(pk=eid)
            messages.success(
                request,
                _("Workspace scope: %(name)s.") % {"name": ent.name},
            )
        else:
            request.session[MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY] = "all"
            messages.success(request, _("Workspace scope: all organizations."))
    else:
        request.session[MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY] = "all"
        messages.success(request, _("Workspace scope: all organizations."))

    next_url = (request.POST.get("next") or "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("manage:dashboard")


@studio_capability_required(*read_or_write(MANAGE_ENTITY_SETTINGS), any_entity=True)
def organization_settings(request):
    """Pick an organization to configure (non-superuser org admins)."""
    eids = entities_with_permission(request.user, *read_or_write(MANAGE_ENTITY_SETTINGS), request=request)
    ents = list(Entity.objects.filter(pk__in=eids).order_by("name"))
    if len(ents) == 1:
        return redirect("manage:organization_settings_hub", pk=ents[0].pk)
    return render(
        request,
        "magicforms/manage/organization_settings_list.html",
        {"entities": ents},
    )


@studio_capability_required(*read_or_write(MANAGE_ENTITY_SETTINGS), entity_pk_kw="pk")
def organization_settings_hub(request, pk):
    ent = get_object_or_404(Entity, pk=pk)
    if not user_has_entity_permission(
        request.user, ent.pk, *read_or_write(MANAGE_ENTITY_SETTINGS), request=request
    ):
        raise Http404
    return render(
        request,
        "magicforms/manage/organization_settings_hub.html",
        {"entity": ent},
    )


@studio_capability_required(MANAGE_ENTITY_SETTINGS_WRITE, entity_pk_kw="pk")
def organization_settings_general(request, pk):
    ent = get_object_or_404(Entity, pk=pk)
    if not user_has_entity_permission(
        request.user, ent.pk, *read_or_write(MANAGE_ENTITY_SETTINGS), request=request
    ):
        raise Http404
    if request.method == "POST":
        f = StaffEntityForm(request.POST, request.FILES, instance=ent)
        if f.is_valid():
            f.save()
            messages.success(request, _("Organization updated."))
            return redirect("manage:organization_settings_hub", pk=ent.pk)
    else:
        f = StaffEntityForm(instance=ent)
    return render(
        request,
        "magicforms/manage/entity_form.html",
        {
            "form": f,
            "mode": "edit",
            "entity_obj": ent,
            "cancel_url": reverse("manage:organization_settings_hub", args=[ent.pk]),
            "save_redirect_hub": True,
        },
    )


@superuser_required
def entity_list(request):
    entities_qs = Entity.objects.order_by("name")
    entities_page, per_page = paginate(request, entities_qs)
    return render(
        request,
        "magicforms/manage/entity_list.html",
        {
            "entities": entities_page,
            "per_page": per_page,
            "per_page_choices": STUDIO_PER_PAGE_CHOICES,
        },
    )


@superuser_required
def entity_add(request):
    if request.method == "POST":
        f = StaffEntityForm(request.POST, request.FILES)
        if f.is_valid():
            ent = f.save()
            from .sample_forms_library import ensure_sample_forms_for_entity_live

            n_samples = ensure_sample_forms_for_entity_live(ent)
            if n_samples:
                messages.success(
                    request,
                    _("Organization created. %(n)d sample starter forms were added.")
                    % {"n": n_samples},
                )
            else:
                messages.success(request, _("Organization created."))
            return redirect("manage:entity_list")
    else:
        f = StaffEntityForm()
    return render(request, "magicforms/manage/entity_form.html", {"form": f, "mode": "add"})


@studio_capability_required(*read_or_write(MANAGE_ENTITY_SETTINGS), entity_pk_kw="pk")
def entity_email_notifications(request, pk):
    ent = get_object_or_404(Entity, pk=pk)
    if not user_may_access_entity(request.user, ent.pk, request=request):
        raise Http404
    from .entity_email import entity_email_notifications_ready
    from .notification_emails import PLACEHOLDER_HELP

    smtp_ok, smtp_message = entity_email_notifications_ready(ent)
    if request.method == "POST":
        if not user_has_entity_permission(
            request.user,
            ent.pk,
            MANAGE_ENTITY_SETTINGS_WRITE,
            request=request,
        ):
            messages.warning(request, _("You do not have write access to organization settings."))
            return redirect("manage:organization_settings_hub", pk=ent.pk)
        f = EntityEmailNotificationsManageForm(ent, request.POST)
        if f.is_valid():
            f.save()
            messages.success(request, _("Email notification templates saved."))
            return redirect("manage:entity_email_notifications", pk=ent.pk)
    else:
        f = EntityEmailNotificationsManageForm(ent)
    template_sections = []
    for kind, label in EntityEmailNotificationTemplate.Kind.choices:
        template_sections.append(
            {
                "kind": kind,
                "label": label,
                "active": f[f"tpl_{kind}_active"],
                "subject": f[f"tpl_{kind}_subject"],
                "body": f[f"tpl_{kind}_body"],
            }
        )
    if request.user.is_superuser:
        cancel_url = reverse("manage:entity_edit", args=[ent.pk])
    elif user_has_entity_permission(
        request.user, ent.pk, *read_or_write(MANAGE_ENTITY_SETTINGS), request=request
    ):
        cancel_url = reverse("manage:organization_settings_hub", args=[ent.pk])
    else:
        cancel_url = reverse("manage:dashboard")
    return render(
        request,
        "magicforms/manage/entity_email_notifications.html",
        {
            "entity": ent,
            "form": f,
            "template_sections": template_sections,
            "placeholder_help": PLACEHOLDER_HELP,
            "smtp_ok": smtp_ok,
            "smtp_message": smtp_message,
            "cancel_url": cancel_url,
        },
    )


@superuser_required
def entity_edit(request, pk):
    ent = get_object_or_404(Entity, pk=pk)
    if request.method == "POST":
        f = StaffEntityForm(request.POST, request.FILES, instance=ent)
        if f.is_valid():
            f.save()
            messages.success(request, _("Organization updated."))
            return redirect("manage:entity_list")
    else:
        f = StaffEntityForm(instance=ent)
    return render(
        request,
        "magicforms/manage/entity_form.html",
        {"form": f, "mode": "edit", "entity_obj": ent},
    )
