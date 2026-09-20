import json
import os
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.db.models import Max, Prefetch, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.utils.translation import gettext as _
from django.core.files.base import ContentFile
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from .dynamic_forms import (
    build_public_form,
    build_visibility_rules,
    field_collects_answer,
    serialize_value,
)
from .user_mapping import build_initial_from_mappings
from .form_layout import build_public_layout_blocks
from .entity_theme import portal_theme_inline
from .opaque_ids import encode as oid_encode
from .models import (
    Entity,
    FieldType,
    Form,
    FormIntroSlide,
    FormLogo,
    FormSubmission,
    SubmissionAttachment,
    SubmissionEvent,
    SubmissionSignaturePlacement,
    SupplementarySubmission,
    UserSignature,
    USER_SIGNATURE_MAX_PER_USER,
)
from .staff_forms import StaffSubmissionAttachmentForm, StaffSubmissionForwardForm, StaffUserSignatureForm
from .attachment_utils import (
    attachment_may_delete_on_track,
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
from .subdomain import portal_redirect, portal_reverse
from .supplementary import (
    ensure_related_invitations,
    record_related_child_submitted,
    respondent_may_access_related_form,
)


def _resolve_portal_entity(request, entity_slug=None):
    portal_entity = getattr(request, "portal_entity", None)
    if getattr(request, "portal_short_urls", False) and portal_entity is not None:
        if entity_slug and entity_slug.lower() != portal_entity.slug.lower():
            raise Http404()
        return portal_entity
    if not entity_slug:
        raise Http404()
    return get_object_or_404(Entity.objects.filter(is_active=True), slug=entity_slug)


def _entity_visual_ctx(entity):
    if entity is None:
        return {}
    return {
        "portal_entity": entity,
        "portal_theme_inline": portal_theme_inline(entity),
    }


def _form_intro_context(
    request,
    form_def,
    *,
    studio_intro_preview: bool = False,
) -> dict:
    from .intro_page import build_intro_page_context

    return {
        **build_intro_page_context(
            request, form_def, studio_intro_preview=studio_intro_preview
        ),
        **_entity_visual_ctx(form_def.entity),
    }


def _render_form_intro(request, form_def, entity, *, studio_intro_preview: bool = False):
    return render(
        request,
        "magicforms/form_intro.html",
        _form_intro_context(
            request,
            form_def,
            studio_intro_preview=studio_intro_preview,
        ),
    )


def _redirect_login_if_form_requires_account(request, form_def):
    """When ``is_for_public`` is off, only signed-in users may open the form."""
    if not form_def.is_for_public and not request.user.is_authenticated:
        from .subdomain import portal_return_url, studio_login_url

        return redirect_to_login(
            portal_return_url(request),
            login_url=studio_login_url(request),
        )
    return None


def _require_published_form_for_public_respondent(form_def) -> None:
    """Draft (unpublished) forms must not be used on any public respondent route."""
    if form_def.is_published:
        return
    raise Http404(
        _(
            "This form is not published yet. If you manage it, open /manage/, edit the form, "
            "and turn on “Published” once you have at least one field and one workflow step."
        )
    )


def _one_time_session_key(form_pk: int) -> str:
    return f"magicforms_onetime_{form_pk}"


def _already_completed_one_time(form_def, request) -> bool:
    if not form_def.one_time_submit:
        return False
    if request.user.is_authenticated:
        if FormSubmission.objects.filter(form=form_def, submitted_by=request.user).exists():
            return True
    if request.session.get(_one_time_session_key(form_def.pk)):
        return True
    return False


def home(request):
    from .entity_access import entity_ids_for_user
    from .subdomain import (
        is_strict_apex_portal_request,
        subdomain_slug_detected,
        unknown_organization_response,
    )

    blocked = unknown_organization_response(request)
    if blocked is not None:
        return blocked

    u = request.user
    if u.is_authenticated and u.is_active:
        if u.is_superuser or bool(entity_ids_for_user(u)):
            # Do not bounce staff off entity portals (e.g. default.swapforms.com).
            on_entity_portal = bool(
                getattr(request, "portal_short_urls", False)
                or subdomain_slug_detected(request)
                or getattr(request, "portal_entity", None)
            )
            if not on_entity_portal and is_strict_apex_portal_request(request):
                return redirect(reverse("manage:dashboard"))

    return render(
        request,
        "magicforms/home.html",
        {
            "studio_available": False,
            "studio_login_next": reverse("manage:dashboard"),
        },
    )


def landing(request):
    """SwapForms landing page at ``/welcome/`` — reachable on every host, including the apex portal."""
    return render(
        request,
        "magicforms/home.html",
        {
            "studio_available": False,
            "studio_login_next": reverse("manage:dashboard"),
        },
    )


def entity_home(request, entity_slug=None):
    """Branded public portal for one organization: open forms, news, theme."""
    from .entity_access import published_forms_for_entity_portal
    from .subdomain import unknown_organization_response

    blocked = unknown_organization_response(request)
    if blocked is not None:
        return blocked

    entity = _resolve_portal_entity(request, entity_slug)
    from .subdomain import reject_mismatched_portal_entity

    if reject_mismatched_portal_entity(request, entity):
        blocked = unknown_organization_response(request)
        if blocked is not None:
            return blocked
    published_forms = list(published_forms_for_entity_portal(entity, request)[:200])
    return render(
        request,
        "magicforms/entity_home.html",
        {
            "entity": entity,
            "published_forms": published_forms,
            **_entity_visual_ctx(entity),
        },
    )


@login_required
def my_signatures(request):
    """Let signed-in users upload and remove their own signature images (for merged documents)."""
    user = request.user
    ctx_base = {
        "signature_limit": USER_SIGNATURE_MAX_PER_USER,
        **_entity_visual_ctx(None),
    }

    if request.method == "POST":
        sig_action = (request.POST.get("signature_action") or "").strip()
        if sig_action == "add":
            if user.signatures.count() >= USER_SIGNATURE_MAX_PER_USER:
                messages.error(
                    request,
                    _("You can have at most %(max)d signature images.")
                    % {"max": USER_SIGNATURE_MAX_PER_USER},
                )
                return redirect("magicforms:my_signatures")
            sig_form = StaffUserSignatureForm(request.POST, request.FILES)
            if sig_form.is_valid():
                obj = sig_form.save(commit=False)
                obj.user = user
                mx = user.signatures.aggregate(mx=Max("sort_order"))["mx"]
                obj.sort_order = (mx if mx is not None else -1) + 1
                obj.save()
                messages.success(request, _("Signature image saved."))
                return redirect("magicforms:my_signatures")
            return render(
                request,
                "magicforms/my_signatures.html",
                {
                    **ctx_base,
                    "signature_add_form": sig_form,
                    "signatures": list(user.signatures.order_by("sort_order", "id")),
                },
            )
        if sig_action == "set_primary":
            sid = (request.POST.get("signature_id") or "").strip()
            if sid.isdigit() and UserSignature.assign_primary(user, int(sid)):
                messages.success(request, _("Primary signature updated."))
            else:
                messages.error(request, _("That signature was not found."))
            return redirect("magicforms:my_signatures")
        if sig_action == "delete":
            sid = (request.POST.get("signature_id") or "").strip()
            if sid.isdigit():
                deleted_count, _ignored = user.signatures.filter(pk=int(sid)).delete()
                if deleted_count:
                    messages.success(request, _("Signature removed."))
                else:
                    messages.error(request, _("That signature was not found."))
            return redirect("magicforms:my_signatures")

    return render(
        request,
        "magicforms/my_signatures.html",
        {
            **ctx_base,
            "signature_add_form": StaffUserSignatureForm(),
            "signatures": list(user.signatures.order_by("sort_order", "id")),
        },
    )


@login_required
def pending_related_list(request):
    """Signed-in applicants: child forms still owed (same account as base submission)."""
    pending_rows = list(
        SupplementarySubmission.objects.filter(
            parent_submission__submitted_by=request.user,
            child_submission__isnull=True,
            link__child_form__is_published=True,
            link__child_form__deleted_at__isnull=True,
        )
        .select_related(
            "link__child_form",
            "link__child_form__entity",
            "parent_submission__form",
        )
        .order_by("-invited_at", "id")
    )
    return render(
        request,
        "magicforms/pending_related_list.html",
        {
            "pending_rows": pending_rows,
            **_entity_visual_ctx(None),
        },
    )


def my_drafts(request):
    """
    Saved drafts to resume: account drafts for signed-in users, plus drafts saved
    in this browser session (guests).
    """
    from .form_drafts import (
        draft_resume_url,
        forget_session_draft,
        session_draft_tokens,
    )
    from .models import FormSubmissionDraft

    cond = Q(resume_token__in=session_draft_tokens(request))
    if request.user.is_authenticated:
        cond |= Q(user=request.user)
    base_qs = (
        FormSubmissionDraft.objects.filter(cond)
        .filter(form__deleted_at__isnull=True, form__is_published=True)
        .select_related("form", "form__entity")
        .order_by("-updated_at")
    )

    if request.method == "POST":
        token = (request.POST.get("delete_draft") or "").strip()
        target = next((d for d in base_qs if str(d.resume_token) == token), None)
        if target is not None:
            forget_session_draft(request, token)
            target.delete()
            messages.success(request, _("Draft deleted."))
        return redirect(request.path)

    draft_rows = [
        {
            "draft": d,
            "resume_url": draft_resume_url(request, d),
            "answers_count": len(d.data or {}),
        }
        for d in base_qs
    ]
    return render(
        request,
        "magicforms/my_drafts.html",
        {
            "draft_rows": draft_rows,
            **_entity_visual_ctx(None),
        },
    )


def form_public_legacy_redirect(request, slug):
    """Old ``/f/<slug>/`` URLs: redirect when the slug is unambiguous within one entity."""
    qs = Form.objects.filter(slug=slug, deleted_at__isnull=True).select_related("entity")
    n = qs.count()
    if n == 1:
        f = qs.first()
        return portal_redirect(
            request,
            "magicforms:form_public",
            entity=f.entity,
            slug=f.slug,
            permanent=True,
        )
    if n == 0:
        raise Http404(
            "No form exists at this address. Check the URL or ask the owner for the correct link."
        )
    raise Http404(
        "This form link is out of date. Please use the full link from your organization "
        "(it starts with /e/…/f/…)."
    )


def submission_detail_legacy_redirect(request, slug, token):
    qs = Form.objects.filter(slug=slug, deleted_at__isnull=True).select_related("entity")
    n = qs.count()
    if n != 1:
        raise Http404("Submission link is invalid or ambiguous. Use the track link you were given.")
    f = qs.first()
    return portal_redirect(
        request,
        "magicforms:submission_detail",
        entity=f.entity,
        slug=f.slug,
        token=token,
        permanent=True,
    )


_TRACK_LOOKUP_MAX_ATTEMPTS = 10
_TRACK_LOOKUP_WINDOW_SECONDS = 15 * 60


def _track_lookup_throttled(request) -> bool:
    """Cache-based throttle: max attempts per client IP per window (5-digit codes are guessable)."""
    from django.core.cache import cache

    ip = (request.META.get("REMOTE_ADDR") or "unknown")[:64]
    key = f"mf_track_lookup_{ip}"
    attempts = cache.get(key, 0)
    if attempts >= _TRACK_LOOKUP_MAX_ATTEMPTS:
        return True
    cache.set(key, attempts + 1, _TRACK_LOOKUP_WINDOW_SECONDS)
    return False


def submission_track(request):
    """
    Public lookup: a respondent enters their email plus the 5-digit track number shown
    after submitting, and is redirected to their submission's track page (status + details).
    """
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    email = ""
    code = ""
    error = ""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()[:254]
        code = "".join(ch for ch in (request.POST.get("code") or "") if ch.isdigit())[:5]
        try:
            validate_email(email)
            email_ok = True
        except ValidationError:
            email_ok = False

        if not email_ok or len(code) != 5:
            error = _("Enter the email you used on the form and your 5-digit track number.")
        elif _track_lookup_throttled(request):
            error = _("Too many attempts. Wait a few minutes and try again.")
        else:
            submission = (
                FormSubmission.objects.filter(track_code=code)
                .filter(
                    Q(submitter_email__iexact=email)
                    | Q(
                        values__field__field_type=FieldType.EMAIL,
                        values__value__iexact=email,
                    )
                )
                .filter(form__deleted_at__isnull=True)
                .select_related("form", "form__entity")
                .order_by("-submitted_at")
                .first()
            )
            if submission is not None:
                return portal_redirect(
                    request,
                    "magicforms:submission_detail",
                    entity=submission.form.entity,
                    slug=submission.form.slug,
                    token=submission.reference_token,
                )
            error = _(
                "No submission matches this email and track number. "
                "Check both and try again."
            )

    return render(
        request,
        "magicforms/submission_track.html",
        {
            "track_email": email,
            "track_code": code,
            "track_error": error,
            **_entity_visual_ctx(None),
        },
    )


def _public_intro_form_access(request, slug, entity_slug=None):
    """Published form with intro enabled; enforces optional ``?share=`` secret."""
    entity = _resolve_portal_entity(request, entity_slug)
    form_def = get_object_or_404(
        Form.objects.filter(deleted_at__isnull=True).select_related("entity"),
        entity=entity,
        slug=slug,
    )
    _require_published_form_for_public_respondent(form_def)
    if not form_def.intro_page_enabled:
        raise Http404()
    if form_def.public_share_key:
        share = (request.GET.get("share") or "").strip()
        if share != str(form_def.public_share_key):
            raise Http404()
    return form_def


def form_intro_qrcode(request, slug, entity_slug=None):
    """PNG QR for the public announcement page URL (same access rules as the intro page)."""
    from django.http import HttpResponse

    from magicforms.qrcode_png import encode_qrcode_png

    form_def = _public_intro_form_access(request, slug, entity_slug=entity_slug)
    url = form_def.build_public_form_absolute_url(request)
    try:
        png = encode_qrcode_png(url)
    except ImportError as exc:
        raise Http404(
            "QR code generation is not available. Install the qrcode package on the server."
        ) from exc
    resp = HttpResponse(png, content_type="image/png")
    if (request.GET.get("download") or "").strip() == "1":
        resp["Content-Disposition"] = (
            f'attachment; filename="announcement-{form_def.slug}-qr.png"'
        )
    resp["Cache-Control"] = "public, max-age=3600"
    return resp


def form_intro_attachment(request, slug, entity_slug=None):
    """Download the optional PDF on a form's information page."""
    entity = _resolve_portal_entity(request, entity_slug)
    form_def = get_object_or_404(
        Form.objects.filter(deleted_at__isnull=True).select_related("entity"),
        entity=entity,
        slug=slug,
    )
    _require_published_form_for_public_respondent(form_def)
    if form_def.public_share_key:
        share = (request.GET.get("share") or "").strip()
        if share != str(form_def.public_share_key):
            raise Http404()
    if not form_def.intro_attachment or not form_def.intro_attachment.name:
        raise Http404()
    try:
        fh = form_def.intro_attachment.open("rb")
    except FileNotFoundError as exc:
        raise Http404() from exc
    basename = os.path.basename(form_def.intro_attachment.name)
    return FileResponse(
        fh,
        as_attachment=True,
        filename=basename,
        content_type="application/pdf",
    )


def _form_has_docx_pdf_output(form_def) -> bool:
    """True when the primary print template is a DOCX and the server can convert it to PDF."""
    primary = form_def.print_template
    if not primary:
        return False
    return (primary.name or "").lower().endswith(".docx") and docx_to_pdf_available()


_SIGN_SESSION_KEY = "magicforms_signable_submissions"


def _remember_signing_session(request, submission) -> None:
    """Public (anonymous) respondents may sign only from the browser session that submitted."""
    tokens = list(request.session.get(_SIGN_SESSION_KEY) or [])
    tokens = [t for t in tokens if t != submission.reference_token]
    tokens.append(submission.reference_token)
    request.session[_SIGN_SESSION_KEY] = tokens[-20:]
    request.session.modified = True


def _signatures_locked_by_workflow(submission) -> bool:
    """True once staff acted: submission left its first step, or was completed / rejected."""
    if submission.workflow_state != FormSubmission.WorkflowState.IN_PROGRESS:
        return True
    if submission.current_step_id:
        first = submission.form.initial_workflow_step()
        if first is None or first.pk != submission.current_step_id:
            return True
    return False


def _signature_lock_reason(request, submission) -> str | None:
    """``None`` when the requester may add or remove signatures, else ``"workflow"`` / ``"identity"``."""
    if _signatures_locked_by_workflow(submission):
        return "workflow"
    user = request.user
    if user.is_authenticated and submission.submitted_by_id and submission.submitted_by_id == user.pk:
        return None
    if submission.form.is_for_public:
        if submission.reference_token in (request.session.get(_SIGN_SESSION_KEY) or []):
            return None
    return "identity"


def _post_submit_redirect(request, entity, form_def, submission):
    """
    After a successful submit: show the filled document (DOCX template merged with every answer,
    rendered as PDF) when available; otherwise the usual tracking page.
    """
    viewname = (
        "magicforms:submission_document"
        if _form_has_docx_pdf_output(form_def)
        else "magicforms:submission_detail"
    )
    return portal_redirect(
        request,
        viewname,
        entity=entity,
        slug=form_def.slug,
        token=submission.reference_token,
    )


def form_public(request, slug, entity_slug=None):
    entity = _resolve_portal_entity(request, entity_slug)
    try:
        form_def = (
            Form.objects.filter(deleted_at__isnull=True)
            .select_related("category", "entity", "submit_validation_config")
            .prefetch_related(
                Prefetch(
                    "logos",
                    queryset=FormLogo.objects.order_by("header_slot", "id"),
                ),
                Prefetch(
                    "intro_slides",
                    queryset=FormIntroSlide.objects.order_by("sort_order", "id"),
                ),
            )
            .get(entity=entity, slug=slug)
        )
    except Form.DoesNotExist:
        raise Http404(
            "No form exists at this address. Check the URL or ask the owner for the correct link."
        )

    _require_published_form_for_public_respondent(form_def)

    login_redir = _redirect_login_if_form_requires_account(request, form_def)
    if login_redir:
        return login_redir

    if form_def.public_share_key:
        share = (request.GET.get("share") or request.POST.get("share") or "").strip()
        if share != str(form_def.public_share_key):
            raise Http404()

    apply_now = (request.GET.get("apply") or request.POST.get("apply") or "").strip() == "1"
    if form_def.intro_page_enabled and not apply_now:
        return _render_form_intro(request, form_def, entity)

    fields = form_def.get_ordered_fields()
    if not fields.exists():
        raise Http404(
            "This form has no fields yet. Add fields in /manage/ before sharing the link."
        )

    if form_def.submission_deadline_has_passed():
        return render(
            request,
            "magicforms/form_public_closed.html",
            {"form_def": form_def, **_entity_visual_ctx(form_def.entity)},
        )

    if form_def.one_time_submit and _already_completed_one_time(form_def, request):
        return render(
            request,
            "magicforms/form_public_one_time.html",
            {"form_def": form_def, **_entity_visual_ctx(form_def.entity)},
        )

    FormClass = build_public_form(form_def)
    mapping_initial = build_initial_from_mappings(request, FormClass._magicforms_fields_def)

    from .form_drafts import (
        collect_draft_post_data,
        draft_accessible,
        draft_form_initial,
        draft_missing_required_labels,
        draft_resume_url,
        find_draft,
        forget_session_draft,
        remember_session_draft,
    )
    from .models import FormSubmissionDraft

    draft_token_raw = (request.GET.get("draft") or request.POST.get("draft_token") or "").strip()
    draft_obj = find_draft(form_def, draft_token_raw)
    if not draft_accessible(draft_obj, request.user):
        draft_obj = None

    if request.method == "POST":
        if form_def.submission_deadline_has_passed():
            return render(
                request,
                "magicforms/form_public_closed.html",
                {"form_def": form_def, **_entity_visual_ctx(form_def.entity)},
            )
        if form_def.one_time_submit and _already_completed_one_time(form_def, request):
            return render(
                request,
                "magicforms/form_public_one_time.html",
                {"form_def": form_def, **_entity_visual_ctx(form_def.entity)},
            )
        if (request.POST.get("save_draft") or "").strip() == "1":
            draft_data = collect_draft_post_data(FormClass, request.POST)
            if draft_obj is not None:
                draft_obj.data = draft_data
                draft_obj.save(update_fields=["data", "updated_at"])
            else:
                draft_obj = FormSubmissionDraft.objects.create(
                    form=form_def,
                    user=request.user if request.user.is_authenticated else None,
                    data=draft_data,
                )
            remember_session_draft(request, draft_obj)
            form = FormClass(
                initial={**mapping_initial, **draft_form_initial(FormClass, draft_obj)}
            )
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
                    "draft_obj": draft_obj,
                    "draft_saved": True,
                    "draft_missing_labels": draft_missing_required_labels(
                        FormClass, draft_data
                    ),
                    "draft_resume_url": draft_resume_url(request, draft_obj),
                    **_entity_visual_ctx(form_def.entity),
                },
            )
        form = FormClass(request.POST, request.FILES)
        if form.is_valid():
            from .submit_validation import check_pre_submit_validation

            force_submit = (request.POST.get("validation_force_submit") or "").strip() == "1"
            validation = check_pre_submit_validation(
                form_def,
                form.cleaned_data,
                FormClass._magicforms_fields_def,
                request,
                force_submit=force_submit,
            )
            if not validation.proceed:
                if not validation.can_force_submit:
                    form.add_error(None, validation.message)
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
                        "validation_warning": validation.message,
                        "validation_can_force": validation.can_force_submit,
                        "draft_obj": draft_obj,
                        **_entity_visual_ctx(form_def.entity),
                    },
                )
            initial_step = form_def.initial_workflow_step()
            submitter_email = ""
            if request.user.is_authenticated:
                submitter_email = (getattr(request.user, "email", None) or "").strip()
            sub = FormSubmission.objects.create(
                form=form_def,
                submitter_email=submitter_email,
                current_step=initial_step,
                submitted_by=request.user if request.user.is_authenticated else None,
            )
            for ff in FormClass._magicforms_fields_def:
                if not field_collects_answer(ff):
                    continue
                key = f"f_{ff.pk}"
                raw = form.cleaned_data.get(key)
                if ff.field_type == FieldType.FILE:
                    defaults = {"value": "", "attachment": None}
                    if raw:
                        defaults["value"] = getattr(raw, "name", "") or ""
                        defaults["attachment"] = raw
                    sub.values.update_or_create(field=ff, defaults=defaults)
                else:
                    sub.values.update_or_create(
                        field=ff,
                        defaults={
                            "value": serialize_value(ff, raw),
                            "attachment": None,
                        },
                    )
            submit_event = SubmissionEvent.objects.create(
                submission=sub,
                kind=SubmissionEvent.Kind.SUBMITTED,
                step=initial_step,
                message="Form submitted.",
            )
            from .workflow_decision import apply_submit_route_role

            apply_submit_route_role(sub)
            ensure_related_invitations(sub)
            from .notification_emails import queue_after_submission_event

            queue_after_submission_event(sub, submit_event, request=request)
            if form_def.one_time_submit:
                request.session[_one_time_session_key(form_def.pk)] = True
                request.session.modified = True
            if draft_obj is not None:
                forget_session_draft(request, str(draft_obj.resume_token))
                draft_obj.delete()
                draft_obj = None
            _remember_signing_session(request, sub)
            return _post_submit_redirect(request, entity, form_def, sub)
    else:
        initial = dict(mapping_initial)
        if draft_obj is not None:
            initial.update(draft_form_initial(FormClass, draft_obj))
        form = FormClass(initial=initial)

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
            "draft_obj": draft_obj,
            **_entity_visual_ctx(form_def.entity),
        },
    )


def related_form_public(request, slug, access_token, entity_slug=None):
    """Applicant-only URL to submit a related (child) form linked to an existing base submission."""
    portal_entity = _resolve_portal_entity(request, entity_slug)
    supp_row = get_object_or_404(
        SupplementarySubmission.objects.select_related(
            "link__child_form",
            "link__child_form__entity",
            "link__parent_form",
            "parent_submission",
            "parent_submission__submitted_by",
            "parent_submission__form",
            "child_submission",
        ),
        access_token=access_token,
    )
    child_form_def = (
        Form.objects.filter(pk=supp_row.link.child_form_id, deleted_at__isnull=True)
        .select_related("category", "entity", "submit_validation_config")
        .prefetch_related(
            Prefetch(
                "logos",
                queryset=FormLogo.objects.order_by("header_slot", "id"),
            ),
            Prefetch(
                "intro_slides",
                queryset=FormIntroSlide.objects.order_by("sort_order", "id"),
            ),
        )
        .get()
    )
    parent_submission = supp_row.parent_submission

    if child_form_def.deleted_at is not None:
        raise Http404()
    path_entity_slug = entity_slug or portal_entity.slug
    if (
        child_form_def.entity.slug.lower() != path_entity_slug.lower()
        or child_form_def.slug.lower() != (slug or "").lower()
    ):
        raise Http404()
    if child_form_def.entity_id != portal_entity.pk or child_form_def.slug != slug:
        return portal_redirect(
            request,
            "magicforms:related_form_public",
            entity=child_form_def.entity,
            slug=child_form_def.slug,
            access_token=access_token,
        )

    _require_published_form_for_public_respondent(child_form_def)

    login_redir = _redirect_login_if_form_requires_account(request, child_form_def)
    if login_redir:
        return login_redir

    if not respondent_may_access_related_form(request, parent_submission):
        return render(
            request,
            "magicforms/related_denied.html",
            {
                "child_form_def": child_form_def,
                "parent_submission": parent_submission,
                **_entity_visual_ctx(child_form_def.entity),
            },
            status=403,
        )

    if supp_row.child_submission_id:
        cs = supp_row.child_submission
        return portal_redirect(
            request,
            "magicforms:submission_detail",
            entity=child_form_def.entity,
            slug=child_form_def.slug,
            token=cs.reference_token,
        )

    fields = child_form_def.get_ordered_fields()
    if not fields.exists():
        raise Http404()

    if child_form_def.submission_deadline_has_passed():
        return render(
            request,
            "magicforms/form_public_closed.html",
            {"form_def": child_form_def, **_entity_visual_ctx(child_form_def.entity)},
        )

    apply_now = (request.GET.get("apply") or request.POST.get("apply") or "").strip() == "1"
    if child_form_def.intro_page_enabled and not apply_now:
        ctx = _form_intro_context(request, child_form_def)
        ctx["apply_url"] = child_form_def.build_related_apply_url(
            request, access_token
        )
        return render(request, "magicforms/form_intro.html", ctx)

    FormClass = build_public_form(child_form_def)
    mapping_initial = build_initial_from_mappings(request, FormClass._magicforms_fields_def)

    if request.method == "POST":
        if child_form_def.submission_deadline_has_passed():
            return render(
                request,
                "magicforms/form_public_closed.html",
                {"form_def": child_form_def, **_entity_visual_ctx(child_form_def.entity)},
            )
        form = FormClass(request.POST, request.FILES)
        if form.is_valid():
            from .submit_validation import check_pre_submit_validation

            force_submit = (request.POST.get("validation_force_submit") or "").strip() == "1"
            validation = check_pre_submit_validation(
                child_form_def,
                form.cleaned_data,
                FormClass._magicforms_fields_def,
                request,
                force_submit=force_submit,
            )
            if not validation.proceed:
                if not validation.can_force_submit:
                    form.add_error(None, validation.message)
                layout_blocks = build_public_layout_blocks(
                    form, FormClass._magicforms_fields_def, child_form_def
                )
                visibility_rules = build_visibility_rules(FormClass._magicforms_fields_def)
                return render(
                    request,
                    "magicforms/form_public.html",
                    {
                        "form_def": child_form_def,
                        "form": form,
                        "layout_blocks": layout_blocks,
                        "visibility_rules": visibility_rules,
                        "validation_warning": validation.message,
                        "validation_can_force": validation.can_force_submit,
                        "related_access_token": access_token,
                        **_entity_visual_ctx(child_form_def.entity),
                    },
                )
            initial_step = child_form_def.initial_workflow_step()
            submitter_email = ""
            if (parent_submission.submitter_email or "").strip():
                submitter_email = parent_submission.submitter_email.strip()
            elif parent_submission.submitted_by_id:
                submitter_email = (
                    getattr(parent_submission.submitted_by, "email", None) or ""
                ).strip()
            sub = FormSubmission.objects.create(
                form=child_form_def,
                submitter_email=submitter_email,
                current_step=initial_step,
                submitted_by=parent_submission.submitted_by,
            )
            supp_row.child_submission = sub
            supp_row.save(update_fields=["child_submission"])
            for ff in FormClass._magicforms_fields_def:
                if not field_collects_answer(ff):
                    continue
                key = f"f_{ff.pk}"
                raw = form.cleaned_data.get(key)
                if ff.field_type == FieldType.FILE:
                    defaults = {"value": "", "attachment": None}
                    if raw:
                        defaults["value"] = getattr(raw, "name", "") or ""
                        defaults["attachment"] = raw
                    sub.values.update_or_create(field=ff, defaults=defaults)
                else:
                    sub.values.update_or_create(
                        field=ff,
                        defaults={
                            "value": serialize_value(ff, raw),
                            "attachment": None,
                        },
                    )
            rel_submit_event = SubmissionEvent.objects.create(
                submission=sub,
                kind=SubmissionEvent.Kind.SUBMITTED,
                step=initial_step,
                message="Form submitted.",
            )
            from .workflow_decision import apply_submit_route_role

            apply_submit_route_role(sub)
            from .notification_emails import queue_after_submission_event

            queue_after_submission_event(sub, rel_submit_event, request=request)
            record_related_child_submitted(parent_submission, child_form_def.title)
            _remember_signing_session(request, sub)
            return _post_submit_redirect(request, child_form_def.entity, child_form_def, sub)
    else:
        form = FormClass(initial=mapping_initial)

    layout_blocks = build_public_layout_blocks(
        form, FormClass._magicforms_fields_def, child_form_def
    )
    visibility_rules = build_visibility_rules(FormClass._magicforms_fields_def)

    return render(
        request,
        "magicforms/form_public.html",
        {
            "form_def": child_form_def,
            "form": form,
            "layout_blocks": layout_blocks,
            "visibility_rules": visibility_rules,
            "related_mode": True,
            "related_parent_title": parent_submission.form.title,
            "related_parent_token_hex": str(parent_submission.reference_token)[:8],
            **_entity_visual_ctx(child_form_def.entity),
        },
    )


def submission_detail(request, slug, token, entity_slug=None):
    entity = _resolve_portal_entity(request, entity_slug)
    form_def = get_object_or_404(
        Form.objects.filter(deleted_at__isnull=True).select_related("entity"),
        entity=entity,
        slug=slug,
    )
    _require_published_form_for_public_respondent(form_def)
    submission = get_object_or_404(
        FormSubmission.objects.select_related("form", "current_step", "submitted_by").prefetch_related(
            "values__field",
            "events__step",
            "events__created_by",
            "document_attachments",
        ),
        reference_token=token,
        form=form_def,
    )
    values = sorted(submission.values.all(), key=lambda v: (v.field.order, v.field_id))
    events = list(submission.events.all())
    document_attachments = list(submission.document_attachments.all())
    track_respondent_upload_open = (
        submission.workflow_state == FormSubmission.WorkflowState.IN_PROGRESS
    )

    ensure_related_invitations(submission)
    related_instances = [
        row
        for row in (
            SupplementarySubmission.objects.filter(parent_submission_id=submission.pk)
            .select_related("link__child_form", "child_submission")
            .prefetch_related("child_submission__values__field")
            .order_by("invited_at", "id")
        )
        if row.link.child_form.deleted_at is None and row.link.child_form.is_published
    ]

    if request.method == "POST":
        if (request.POST.get("applicant_chat_reply") or "").strip() == "1":
            from .models import SubmissionApplicantMessage
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
                    author=request.user if request.user.is_authenticated else None,
                    is_from_applicant=True,
                    body=body[:max_len],
                )
                dispatch_applicant_chat_email(submission, chat_msg, request=request)
                messages.success(
                    request,
                    _("Message sent. The team handling your request was notified."),
                )
            return portal_redirect(
                request,
                "magicforms:submission_detail",
                entity=entity,
                slug=slug,
                token=token,
            )

        forward_action = (request.POST.get("submission_forward") or "").strip()
        if forward_action == "1":
            if not request.user.is_authenticated or submission.submitted_by_id != request.user.pk:
                messages.error(
                    request,
                    _("You can only forward a submission you made while signed in."),
                )
            elif not form_def.allow_submission_forward:
                messages.error(request, _("Forwarding is not enabled for this form."))
            else:
                fwd_form = StaffSubmissionForwardForm(
                    request.POST,
                    actor=request.user,
                    form_entity_id=form_def.entity_id,
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
            return portal_redirect(
                request,
                "magicforms:submission_detail",
                entity=entity,
                slug=slug,
                token=token,
            )

        if request.POST.get("submission_attachment_action") == "delete":
            aid = (request.POST.get("attachment_id") or "").strip()
            if aid.isdigit():
                att = submission.document_attachments.filter(pk=int(aid)).first()
                if att and attachment_may_delete_on_track(request.user, submission, att):
                    fname = os.path.basename(att.file.name) if att.file else ""
                    att.delete()
                    SubmissionEvent.objects.create(
                        submission=submission,
                        kind=SubmissionEvent.Kind.NOTE,
                        step=submission.current_step if submission.current_step_id else None,
                        message=_("Attachment removed: %(name)s") % {"name": fname or str(aid)},
                        created_by=request.user if request.user.is_authenticated else None,
                    )
                    messages.success(request, _("Attachment removed."))
                elif att:
                    messages.error(
                        request,
                        _("You do not have permission to remove this attachment."),
                    )
                else:
                    messages.error(request, _("Attachment not found."))
            return portal_redirect(
                request,
                "magicforms:submission_detail",
                entity=entity,
                slug=slug,
                token=token,
            )

        if request.POST.get("submission_attachment_action") == "add":
            if not track_respondent_upload_open:
                messages.error(
                    request,
                    _("This submission is closed. You cannot upload more documents here."),
                )
                return portal_redirect(
                    request,
                    "magicforms:submission_detail",
                    entity=entity,
                    slug=slug,
                    token=token,
                )
            att_form = StaffSubmissionAttachmentForm(
                request.POST,
                request.FILES,
                submission=submission,
            )
            if att_form.is_valid():
                att = att_form.save(commit=False)
                att.submission = submission
                att.uploaded_by = None
                att.save()
                fname = os.path.basename(att.file.name) if att.file else ""
                msg = f"Document added: {fname}"
                if att.title:
                    msg = f"{msg} — {att.title}"
                SubmissionEvent.objects.create(
                    submission=submission,
                    kind=SubmissionEvent.Kind.ATTACHMENT_ADDED,
                    step=submission.current_step if submission.current_step_id else None,
                    message=msg[:1000],
                    created_by=None,
                )
                messages.success(request, _("Your document was uploaded."))
            else:
                for errs in att_form.errors.values():
                    for err in errs:
                        messages.error(request, str(err))
            return portal_redirect(
                request,
                "magicforms:submission_detail",
                entity=entity,
                slug=slug,
                token=token,
            )

    attachment_form = (
        StaffSubmissionAttachmentForm(submission=submission)
        if track_respondent_upload_open
        else None
    )

    respondent_forward_form = None
    if (
        form_def.allow_submission_forward
        and request.user.is_authenticated
        and submission.submitted_by_id == request.user.pk
    ):
        respondent_forward_form = StaffSubmissionForwardForm(
            actor=request.user,
            form_entity_id=form_def.entity_id,
        )

    pc = print_template_merge_capabilities(form_def)
    pl = str(pc["primary_name_lower"] or "")
    submission_print = {
        "has_merge_output": pc["has_merge_output"],
        "merged_pdf_available": pc["merged_pdf_available"],
        "show_docx_download": pc["show_docx_download"],
        "show_odt_download": pc["show_odt_download"],
        "has_odt_secondary": pc["has_odt_secondary"],
        "print_is_docx": bool(pc["has_print_template"]) and pl.endswith(".docx"),
        "pdf_inline_path": "",
    }
    if pc["merged_pdf_available"]:
        submission_print["pdf_inline_path"] = (
            portal_reverse(
                request,
                "magicforms:submission_merged_document",
                entity=entity,
                kwargs={"slug": slug, "token": token, "fmt": "pdf"},
            )
            + "?inline=1"
        )

    submission_attachment_rows = []
    for doc in document_attachments:
        ext = attachment_source_ext_for_pdf(doc)
        lo = bool(ext and docx_to_pdf_available())
        pdf_inline_path = ""
        if lo:
            pdf_inline_path = (
                portal_reverse(
                    request,
                    "magicforms:submission_attachment_pdf",
                    entity=entity,
                    kwargs={
                        "slug": slug,
                        "token": token,
                        "attachment_id": doc.pk,
                    },
                )
                + "?inline=1"
            )
        submission_attachment_rows.append(
            {
                "doc": doc,
                "may_delete": attachment_may_delete_on_track(request.user, submission, doc),
                "pdf_inline_path": pdf_inline_path,
            }
        )

    return render(
        request,
        "magicforms/submission_detail.html",
        {
            "form_def": form_def,
            "submission": submission,
            "values": values,
            "events": events,
            "document_attachments": document_attachments,
            "attachment_form": attachment_form,
            "track_respondent_upload_open": track_respondent_upload_open,
            "attachment_max": SubmissionAttachment.MAX_PER_SUBMISSION,
            "related_instances": related_instances,
            "respondent_forward_form": respondent_forward_form,
            "submission_print": submission_print,
            "submission_attachment_rows": submission_attachment_rows,
            "applicant_chat_messages": list(
                submission.applicant_messages.select_related("author").order_by("created_at")
            ),
            **_entity_visual_ctx(form_def.entity),
        },
    )


@xframe_options_sameorigin
def submission_attachment_pdf(request, slug, token, attachment_id, entity_slug=None):
    """Convert a submission attachment (DOC, DOCX, or ODT) to PDF for in-browser preview (track link)."""
    inline = request.GET.get("inline") in ("1", "true", "yes")
    entity = _resolve_portal_entity(request, entity_slug)
    form_def = get_object_or_404(
        Form.objects.filter(deleted_at__isnull=True).select_related("entity"),
        entity=entity,
        slug=slug,
    )
    _require_published_form_for_public_respondent(form_def)
    submission = get_object_or_404(
        FormSubmission,
        reference_token=token,
        form=form_def,
    )
    att = get_object_or_404(SubmissionAttachment, pk=attachment_id, submission=submission)
    ext = attachment_source_ext_for_pdf(att)
    if not ext or not docx_to_pdf_available():
        msg = _("PDF preview is not available for this file.")
        if inline:
            return HttpResponse(str(msg), status=400, content_type="text/plain; charset=utf-8")
        messages.error(request, msg)
        return portal_redirect(
            request,
            "magicforms:submission_detail",
            entity=entity,
            slug=slug,
            token=token,
        )
    try:
        att.file.open("rb")
        try:
            raw = att.file.read()
        finally:
            att.file.close()
        pdf_bytes = libreoffice_bytes_to_pdf(raw, f"attachment_{att.pk}", ext)
        pdf_bytes = stamp_entity_logo_on_pdf(pdf_bytes, form_def.entity)
    except PrintMergeError as exc:
        if inline:
            return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
        messages.error(request, str(exc))
        return portal_redirect(
            request,
            "magicforms:submission_detail",
            entity=entity,
            slug=slug,
            token=token,
        )
    stem = get_valid_filename(os.path.splitext(os.path.basename(att.file.name))[0])[:120] or f"attachment_{att.pk}"
    return FileResponse(
        BytesIO(pdf_bytes),
        as_attachment=not inline,
        filename=f"{stem}.pdf",
        content_type="application/pdf",
    )


@xframe_options_sameorigin
def submission_document(request, slug, token, entity_slug=None):
    """
    Post-submit landing page: only the filled document (DOCX print template merged with the
    answers, shown as PDF). Falls back to the tracking page when the form has no DOCX template
    or PDF conversion is unavailable.
    """
    entity = _resolve_portal_entity(request, entity_slug)
    form_def = get_object_or_404(
        Form.objects.filter(deleted_at__isnull=True).select_related("entity"),
        entity=entity,
        slug=slug,
    )
    _require_published_form_for_public_respondent(form_def)
    submission = get_object_or_404(
        FormSubmission.objects.select_related("form"),
        reference_token=token,
        form=form_def,
    )
    if not _form_has_docx_pdf_output(form_def):
        return portal_redirect(
            request,
            "magicforms:submission_detail",
            entity=entity,
            slug=slug,
            token=token,
        )
    pdf_inline_path = (
        portal_reverse(
            request,
            "magicforms:submission_merged_document",
            entity=entity,
            kwargs={"slug": slug, "token": token, "fmt": "pdf"},
        )
        + "?inline=1"
    )
    sign_urls = {
        "place": portal_reverse(
            request,
            "magicforms:submission_signature_place",
            entity=entity,
            kwargs={"slug": slug, "token": token},
        ),
        "remove_template": portal_reverse(
            request,
            "magicforms:submission_signature_remove",
            entity=entity,
            kwargs={"slug": slug, "token": token, "placement_id": 0},
        ),
    }
    return render(
        request,
        "magicforms/submission_document.html",
        {
            "form_def": form_def,
            "submission": submission,
            "pdf_inline_path": pdf_inline_path,
            "sign_urls": sign_urls,
            "signature_placements": _signature_placements_payload(submission),
            "sign_i18n": _signature_sign_i18n(),
            "sign_lock_reason": _signature_lock_reason(request, submission),
            **_entity_visual_ctx(form_def.entity),
        },
    )


_SIGNATURE_SEALING_EVENT_KINDS = (
    SubmissionEvent.Kind.STEP_APPROVED,
    SubmissionEvent.Kind.WORKFLOW_COMPLETED,
    SubmissionEvent.Kind.WORKFLOW_REJECTED,
)


def _signature_sealed_after(submission):
    """
    Timestamp of the latest decision still standing, or ``None``. Signatures placed before it are sealed.
    An "Undo approve" cancels the approval it reverts, so signatures placed before that approval become
    removable again.
    """
    kinds = _SIGNATURE_SEALING_EVENT_KINDS + (SubmissionEvent.Kind.APPROVE_UNDONE,)
    standing: list = []
    for kind, created_at in (
        submission.events.filter(kind__in=kinds).order_by("created_at", "id").values_list("kind", "created_at")
    ):
        if kind == SubmissionEvent.Kind.APPROVE_UNDONE:
            for i in range(len(standing) - 1, -1, -1):
                if standing[i][0] in (SubmissionEvent.Kind.STEP_APPROVED, SubmissionEvent.Kind.WORKFLOW_COMPLETED):
                    del standing[i]
                    break
        else:
            standing.append((kind, created_at))
    return standing[-1][1] if standing else None


def signature_is_sealed(submission, placement) -> bool:
    """A signature can no longer be removed once someone approved or rejected after it was placed."""
    last = _signature_sealed_after(submission)
    return bool(last and placement.created_at <= last)


def _signature_placements_payload(submission) -> list[dict]:
    last = _signature_sealed_after(submission)
    return [
        {
            "id": oid_encode(p.pk),
            "page": p.page_index,
            "x": p.x,
            "y": p.y,
            "width": p.width,
            "locked": bool(last and p.created_at <= last),
        }
        for p in submission.signature_placements.all()
    ]


def _signature_sign_i18n() -> dict:
    return {
        "loading": _("Loading document…"),
        "load_failed": _("The document could not be displayed. Use Download PDF instead."),
        "page": _("Page %(n)s"),
        "placed": _("Signature placed."),
        "removed": _("Signature removed."),
        "empty": _("Draw your signature before placing it."),
        "network": _("Could not reach the server. Check your connection and try again."),
        "confirm_remove": _("Remove this signature?"),
        "placement_label": _("Signature %(n)s · page %(page)s"),
        "remove": _("Remove"),
        "placing": _("Placing…"),
        "updating": _("Updating the document with your signature…"),
        "removing": _("Removing the signature…"),
        "sealed": _("Sealed: a decision was made after this signature was placed."),
        "placing_saved": _("Placing your saved signature…"),
        "update_title": _("Update your signature"),
        "update_help": _("Draw it again. This replaces the saved signature used for right-click placement."),
        "update_button": _("Save signature"),
        "updating_signature": _("Saving…"),
        "updated": _("Signature updated."),
        "draw_title": _("Draw your signature"),
        "draw_help": _("Use your mouse or finger. The signature will be placed where you clicked."),
        "place_button": _("Place signature"),
        "saved_next_time": _("Signature placed. Approve or reject to keep it as your signature for next time."),
    }


def _document_page_submission(request, slug, token, entity_slug):
    entity = _resolve_portal_entity(request, entity_slug)
    form_def = get_object_or_404(
        Form.objects.filter(deleted_at__isnull=True).select_related("entity"),
        entity=entity,
        slug=slug,
    )
    _require_published_form_for_public_respondent(form_def)
    submission = get_object_or_404(FormSubmission.objects.select_related("form"), reference_token=token, form=form_def)
    return entity, form_def, submission


_SIGN_LOCK_MESSAGES = {
    "workflow": _("This document is locked because it is already being processed."),
    "identity": _("Only the person who submitted this form can change its signatures."),
}


def _signature_lock_response(request, submission):
    reason = _signature_lock_reason(request, submission)
    if reason is None:
        return None
    return JsonResponse({"ok": False, "error": _SIGN_LOCK_MESSAGES[reason], "locked": reason}, status=403)


@require_POST
def submission_signature_place(request, slug, token, entity_slug=None):
    """Store a drawn signature at a point on the merged PDF (page + fractions of the displayed page)."""
    entity, form_def, submission = _document_page_submission(request, slug, token, entity_slug)
    denied = _signature_lock_response(request, submission)
    if denied:
        return denied
    return signature_place_response(request, submission)


def signature_place_response(request, submission, *, allow_saved=False, remember_drawing=False):
    """
    Shared by the public document page and the studio panel: validate the payload, stamp, log, answer JSON.

    ``allow_saved`` lets the payload name one of the requester's stored signatures (``saved_signature_id``)
    instead of a drawing. ``remember_drawing`` stores a first drawing as the user's signature for next time.
    """
    from .pdf_signatures import (
        SIGNATURE_DEFAULT_WIDTH_FRACTION,
        SIGNATURE_MAX_WIDTH_FRACTION,
        SIGNATURE_MIN_WIDTH_FRACTION,
        decode_signature_data_url,
        normalize_signature_file_bytes,
    )

    try:
        payload = json.loads(request.body.decode() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": _("Invalid request.")}, status=400)
    try:
        page_index = int(payload.get("page", 0))
        x = float(payload.get("x"))
        y = float(payload.get("y"))
        width = float(payload.get("width") or SIGNATURE_DEFAULT_WIDTH_FRACTION)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": _("Invalid request.")}, status=400)
    if page_index < 0 or page_index > 500 or not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return JsonResponse({"ok": False, "error": _("Invalid request.")}, status=400)
    width = min(max(width, SIGNATURE_MIN_WIDTH_FRACTION), SIGNATURE_MAX_WIDTH_FRACTION)
    if submission.signature_placements.count() >= 20:
        return JsonResponse({"ok": False, "error": _("Too many signatures on this document.")}, status=400)
    saved_id = payload.get("saved_signature_id")
    remember_candidate = False
    if allow_saved and saved_id and request.user.is_authenticated:
        saved = UserSignature.objects.filter(user=request.user, pk=saved_id).first()
        if saved is None:
            return JsonResponse({"ok": False, "error": _("Saved signature not found.")}, status=400)
        try:
            with saved.image.open("rb") as fh:
                png = normalize_signature_file_bytes(fh.read())
        except (OSError, ValueError) as exc:
            return JsonResponse({"ok": False, "error": str(exc) or _("Saved signature could not be read.")}, status=400)
    else:
        try:
            png = decode_signature_data_url(payload.get("image"))
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        # The drawing becomes the user's stored signature only once they approve or reject (see remember_signature_from_placement).
        remember_candidate = bool(remember_drawing and request.user.is_authenticated and not request.user.signatures.exists())

    placement = SubmissionSignaturePlacement(
        submission=submission,
        page_index=page_index,
        x=x,
        y=y,
        width=width,
        created_by=request.user if request.user.is_authenticated else None,
    )
    placement.image.save("signature.png", ContentFile(png), save=False)
    placement.save()
    SubmissionEvent.objects.create(
        submission=submission,
        kind=SubmissionEvent.Kind.NOTE,
        message=f"Signature placed on the document (page {page_index + 1}).",
        created_by=request.user if request.user.is_authenticated else None,
    )
    return JsonResponse(
        {
            "ok": True,
            "placement_id": oid_encode(placement.pk),
            "placements": _signature_placements_payload(submission),
            "remember_candidate": oid_encode(placement.pk) if remember_candidate else None,
        }
    )


@login_required
@require_POST
def my_signature_replace(request):
    """Studio "Update signature": redraw replaces the user's primary stored signature (or creates the first one)."""
    from .pdf_signatures import decode_signature_data_url

    try:
        payload = json.loads(request.body.decode() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": _("Invalid request.")}, status=400)
    try:
        png = decode_signature_data_url(payload.get("image"))
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    sig = request.user.signatures.order_by("sort_order", "id").first()
    if sig is None:
        sig = UserSignature(user=request.user, label=str(_("Drawn on a document")), sort_order=0)
    else:
        sig.image.delete(save=False)
    sig.image.save("signature.png", ContentFile(png), save=False)
    sig.save()
    return JsonResponse({"ok": True, "id": sig.pk, "url": sig.image.url})


def remember_signature_from_placement(user, submission, placement_id) -> bool:
    """
    Studio: after an approve/reject, keep the drawing the user just placed as their stored signature
    (only when they have none yet, and only their own placement on this submission).
    """
    from .opaque_ids import parse_id

    pk = parse_id(placement_id)
    if not pk or not getattr(user, "is_authenticated", False) or user.signatures.exists():
        return False
    placement = SubmissionSignaturePlacement.objects.filter(pk=pk, submission=submission, created_by=user).first()
    if placement is None:
        return False
    try:
        with placement.image.open("rb") as fh:
            png = fh.read()
    except OSError:
        return False
    sig = UserSignature(user=user, label=str(_("Drawn on a document")), sort_order=0)
    sig.image.save("signature.png", ContentFile(png), save=False)
    sig.save()
    return True


@require_POST
def submission_signature_remove(request, slug, token, placement_id, entity_slug=None):
    entity, form_def, submission = _document_page_submission(request, slug, token, entity_slug)
    denied = _signature_lock_response(request, submission)
    if denied:
        return denied
    return signature_remove_response(request, submission, placement_id)


def signature_remove_response(request, submission, placement_id):
    placement = get_object_or_404(SubmissionSignaturePlacement, pk=placement_id, submission=submission)
    if signature_is_sealed(submission, placement):
        return JsonResponse(
            {
                "ok": False,
                "error": _("This signature is sealed: it was approved or rejected after being placed and cannot be removed."),
                "locked": "decided",
            },
            status=403,
        )
    page_no = placement.page_index + 1
    placement.image.delete(save=False)
    placement.delete()
    SubmissionEvent.objects.create(
        submission=submission,
        kind=SubmissionEvent.Kind.NOTE,
        message=f"Signature removed from the document (page {page_no}).",
        created_by=request.user if request.user.is_authenticated else None,
    )
    return JsonResponse({"ok": True, "placements": _signature_placements_payload(submission)})


@xframe_options_sameorigin
def submission_merged_document(request, slug, token, fmt, entity_slug=None):
    """Merged print template (DOCX / PDF / ODT) for anyone with the secret track link. Use ``?inline=1`` for PDF embed."""
    fmt = (fmt or "").lower()
    if fmt not in ("docx", "pdf", "odt"):
        raise Http404("Unsupported format.")
    inline = request.GET.get("inline") in ("1", "true", "yes")
    entity = _resolve_portal_entity(request, entity_slug)
    form_def = get_object_or_404(
        Form.objects.filter(deleted_at__isnull=True).select_related("entity"),
        entity=entity,
        slug=slug,
    )
    _require_published_form_for_public_respondent(form_def)
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
        reference_token=token,
        form=form_def,
    )
    try:
        data, filename, content_type = render_submission_document(submission, fmt)
    except PrintMergeError as exc:
        if inline:
            return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
        messages.error(request, str(exc))
        return portal_redirect(
            request,
            "magicforms:submission_detail",
            entity=entity,
            slug=slug,
            token=token,
        )
    from .print_merge import merged_document_http_response

    return merged_document_http_response(
        data, filename, content_type, inline=inline
    )
