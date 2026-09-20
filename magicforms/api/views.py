"""Mobile API views (v1)."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from magicforms.api.decorators import mobile_api_errors, mobile_token_required
from magicforms.mobile_auth import (
    authenticate_for_mobile,
    bearer_token_from_request,
    create_mobile_token,
    entities_for_mobile_user,
    revoke_mobile_token,
    user_may_use_mobile_api,
    user_payload,
)


def _parse_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _error(
    message: str,
    *,
    code: str = "error",
    status: int = 400,
    extra: dict | None = None,
) -> JsonResponse:
    body: dict = {"ok": False, "error": code, "message": message}
    if extra:
        body.update(extra)
    return JsonResponse(body, status=status)


@csrf_exempt
@require_POST
@mobile_api_errors
def auth_login(request):
    data = _parse_json_body(request)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    entity_slug = (data.get("entity_slug") or data.get("organization_slug") or "").strip()

    user, login_via, err, entity_choices = authenticate_for_mobile(
        username=username,
        password=password,
        entity_slug=entity_slug,
    )

    if err == "organization_required":
        return _error(
            "Use organization-username (e.g. your-org-jdoe).",
            code="organization_required",
            status=400,
            extra={"entities": entity_choices or []},
        )

    if user is None:
        messages = {
            "invalid_credentials": "Invalid username or password.",
            "inactive_account": "This account is inactive.",
        }
        return _error(
            messages.get(err or "", "Sign-in failed."),
            code=err or "invalid_credentials",
            status=401,
        )

    if not user_may_use_mobile_api(user):
        return _error(
            "This account is not linked to an organization portal.",
            code="portal_access_denied",
            status=403,
        )

    token_row = create_mobile_token(user)
    expires_at = token_row.expires_at.isoformat()
    return JsonResponse(
        {
            "ok": True,
            "token": token_row.key,
            "expires_at": expires_at,
            "token_type": "Bearer",
            "login_via": login_via,
            "user": user_payload(user),
            "entities": entities_for_mobile_user(user, request),
        }
    )


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
@mobile_api_errors
def auth_logout(request):
    key = bearer_token_from_request(request)
    user = None
    if key:
        from magicforms.mobile_auth import user_from_mobile_token

        user = user_from_mobile_token(key)
    if revoke_mobile_token(key):
        if user is not None:
            from magicforms.api.mobile_devices import deactivate_push_devices_for_user

            deactivate_push_devices_for_user(user)
        return JsonResponse({"ok": True})
    return _error("Invalid or expired token.", code="authentication_required", status=401)


@require_GET
@mobile_token_required
@mobile_api_errors
def auth_me(request):
    user = request.mobile_user
    return JsonResponse(
        {
            "ok": True,
            "user": user_payload(user),
            "entities": entities_for_mobile_user(user, request),
        }
    )


@require_GET
@mobile_api_errors
def auth_directory_entities(request):
    """Organizations that require ``entity_slug`` on directory login (no auth)."""
    from magicforms.login_api import entities_with_active_login_api

    entities = [
        {"slug": e.slug, "name": e.name}
        for e in entities_with_active_login_api()
    ]
    return JsonResponse({"ok": True, "entities": entities})


@require_GET
@mobile_token_required
@mobile_api_errors
def home_summary(request):
    from magicforms.api.mobile_content import mobile_home_summary

    return JsonResponse({"ok": True, **mobile_home_summary(request)})


@require_GET
@mobile_token_required
@mobile_api_errors
def forms_published(request):
    from magicforms.api.mobile_content import published_forms_payload

    return JsonResponse({"ok": True, "forms": published_forms_payload(request)})


@require_GET
@mobile_token_required
@mobile_api_errors
def form_intro(request, form_id):
    from django.shortcuts import get_object_or_404

    from magicforms.api.mobile_content import user_may_access_published_form
    from magicforms.intro_page import serialize_form_intro_api
    from magicforms.models import Form

    user = request.mobile_user
    form_def = get_object_or_404(
        Form.objects.filter(deleted_at__isnull=True, is_published=True)
        .select_related("entity")
        .prefetch_related("intro_slides"),
        pk=form_id,
    )
    if not user_may_access_published_form(user, form_def, request):
        return _error("Form not found.", code="not_found", status=404)
    if not form_def.intro_page_enabled:
        return _error(
            "This form has no announcement page.",
            code="intro_disabled",
            status=404,
        )
    return JsonResponse(
        {"ok": True, "intro": serialize_form_intro_api(request, form_def)}
    )


@require_GET
@mobile_token_required
@mobile_api_errors
def form_schema(request, form_id: int):
    from magicforms.api.mobile_form_submit import form_schema_payload

    return JsonResponse({"ok": True, **form_schema_payload(request, form_id)})


@csrf_exempt
@require_POST
@mobile_token_required
@mobile_api_errors
def form_submit(request, form_id: int):
    from magicforms.api.mobile_form_submit import form_submit_payload

    body, status = form_submit_payload(request, form_id)
    return JsonResponse(body, status=status)


@require_GET
@mobile_token_required
@mobile_api_errors
def inbox_list(request):
    from magicforms.api.mobile_content import inbox_list_payload

    try:
        limit = min(100, max(1, int(request.GET.get("limit", "50"))))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(request.GET.get("offset", "0")))
    except (TypeError, ValueError):
        offset = 0
    return JsonResponse({"ok": True, **inbox_list_payload(request, limit=limit, offset=offset)})


@require_GET
@mobile_token_required
@mobile_api_errors
def submissions_search(request):
    from magicforms.api.mobile_submission_search import submission_search_payload

    try:
        limit = min(100, max(1, int(request.GET.get("limit", "50"))))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(request.GET.get("offset", "0")))
    except (TypeError, ValueError):
        offset = 0
    return JsonResponse(
        {"ok": True, **submission_search_payload(request, limit=limit, offset=offset)}
    )


@require_GET
@mobile_token_required
@mobile_api_errors
def inbox_detail(request, submission_id: int):
    from magicforms.api.mobile_content import inbox_detail_payload

    return JsonResponse({"ok": True, **inbox_detail_payload(request, submission_id)})


@csrf_exempt
@require_POST
@mobile_token_required
@mobile_api_errors
def inbox_workflow(request, submission_id: int):
    from magicforms.api.mobile_content import _get_submission_for_mobile
    from magicforms.workflow_decision import perform_workflow_decision

    data = _parse_json_body(request)
    decision = (data.get("decision") or "").strip().lower()
    comment = (data.get("comment") or data.get("workflow_decision_comment") or "").strip()
    anchor_raw = data.get("workflow_action_anchor")
    workflow_anchor: int | None = None
    if anchor_raw is not None and str(anchor_raw).strip() != "":
        try:
            workflow_anchor = int(anchor_raw)
        except (TypeError, ValueError):
            return _error(
                "Invalid workflow action. Refresh and try again.",
                code="invalid_anchor",
                status=400,
            )

    submission = _get_submission_for_mobile(request, submission_id)
    ok, err, result = perform_workflow_decision(
        user=request.mobile_user,
        submission=submission,
        decision=decision,
        comment=comment,
        workflow_action_anchor=workflow_anchor,
    )
    if not ok:
        return _error(err or "Workflow action failed.", code="workflow_error", status=400)
    from magicforms.api.mobile_content import inbox_detail_payload

    detail = inbox_detail_payload(request, submission_id)
    body = {"ok": True, "message": (result or {}).get("message", "Done."), **detail}
    return JsonResponse(body)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@mobile_token_required
@mobile_api_errors
def signatures(request):
    if request.method == "GET":
        from magicforms.api.mobile_signatures import signatures_list_payload

        return JsonResponse({"ok": True, **signatures_list_payload(request)})

    from magicforms.api.mobile_signatures import (
        create_signature_from_upload,
        serialize_signature,
    )
    from magicforms.models import USER_SIGNATURE_MAX_PER_USER

    label = (request.POST.get("label") or "").strip()
    try:
        sig = create_signature_from_upload(request, label=label)
    except ValueError as exc:
        code = str(exc)
        if code == "limit_reached":
            return _error(
                f"You can have at most {USER_SIGNATURE_MAX_PER_USER} signature images.",
                code="limit_reached",
                status=400,
            )
        return _error("Signature image is required.", code="image_required", status=400)

    is_primary = request.mobile_user.signatures.order_by("sort_order", "id").first().pk == sig.pk
    return JsonResponse(
        {
            "ok": True,
            "message": "Signature saved.",
            "signature": serialize_signature(request, sig, is_primary=is_primary),
        }
    )


@csrf_exempt
@require_POST
@mobile_token_required
@mobile_api_errors
def signature_replace_image(request, signature_id: int):
    from magicforms.api.mobile_signatures import (
        replace_signature_image,
        serialize_signature,
    )

    try:
        sig = replace_signature_image(request, signature_id)
    except ValueError:
        return _error("Signature image is required.", code="image_required", status=400)

    primary_pk = (
        request.mobile_user.signatures.order_by("sort_order", "id").values_list("pk", flat=True).first()
    )
    return JsonResponse(
        {
            "ok": True,
            "message": "Signature updated.",
            "signature": serialize_signature(request, sig, is_primary=(sig.pk == primary_pk)),
        }
    )


@csrf_exempt
@require_POST
@mobile_token_required
@mobile_api_errors
def signature_set_primary(request, signature_id: int):
    from magicforms.api.mobile_signatures import set_primary_signature

    if set_primary_signature(request, signature_id):
        return JsonResponse({"ok": True, "message": "Primary signature updated."})
    return _error("That signature was not found.", code="not_found", status=404)


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
@mobile_token_required
@mobile_api_errors
def signature_delete(request, signature_id: int):
    from magicforms.api.mobile_signatures import delete_signature

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if not action and request.body:
            try:
                data = _parse_json_body(request)
                action = (data.get("action") or "").strip()
            except Exception:
                pass
        if action != "delete":
            return _error("Unknown action.", code="invalid_action", status=400)

    if delete_signature(request, signature_id):
        return JsonResponse({"ok": True, "message": "Signature removed."})
    return _error("That signature was not found.", code="not_found", status=404)


@require_GET
@mobile_token_required
@mobile_api_errors
def related_pending(request):
    from magicforms.api.mobile_related import pending_related_payload

    return JsonResponse({"ok": True, **pending_related_payload(request)})


@require_GET
@mobile_token_required
@mobile_api_errors
def related_form_schema(request, access_token):
    from magicforms.api.mobile_related import related_form_schema_payload

    return JsonResponse({"ok": True, **related_form_schema_payload(request, access_token)})


@csrf_exempt
@require_POST
@mobile_token_required
@mobile_api_errors
def related_form_submit(request, access_token):
    from magicforms.api.mobile_related import related_form_submit_payload

    body, status = related_form_submit_payload(request, access_token)
    return JsonResponse(body, status=status)


@require_GET
@mobile_token_required
@mobile_api_errors
def inbox_thread(request, submission_id: int):
    from magicforms.api.mobile_thread import thread_messages_payload

    return JsonResponse({"ok": True, **thread_messages_payload(request, submission_id)})


@csrf_exempt
@require_POST
@mobile_token_required
@mobile_api_errors
def inbox_thread_post(request, submission_id: int):
    from magicforms.api.mobile_thread import thread_post_payload

    data = _parse_json_body(request)
    body = (data.get("body") or data.get("message") or "").strip()
    payload, status = thread_post_payload(request, submission_id, body)
    return JsonResponse(payload, status=status)


@require_GET
@mobile_token_required
@mobile_api_errors
def inbox_value_attachment(request, submission_id: int, value_id: int):
    from magicforms.api.mobile_files import submission_value_attachment

    return submission_value_attachment(request, submission_id, value_id)


@csrf_exempt
@require_POST
@mobile_token_required
@mobile_api_errors
def device_register(request):
    from magicforms.api.mobile_devices import register_push_device

    data = _parse_json_body(request)
    platform = (data.get("platform") or "").strip()
    token = (data.get("token") or "").strip()
    device_id = (data.get("device_id") or "").strip()
    try:
        register_push_device(
            user=request.mobile_user,
            platform=platform,
            token=token,
            device_id=device_id,
        )
    except ValueError as exc:
        return _error(str(exc), status=400)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
@mobile_token_required
@mobile_api_errors
def device_unregister(request):
    from magicforms.api.mobile_devices import deactivate_push_devices_for_user

    data = _parse_json_body(request)
    token = (data.get("token") or "").strip() or None
    count = deactivate_push_devices_for_user(request.mobile_user, token=token)
    return JsonResponse({"ok": True, "deactivated": count})


@require_GET
@mobile_token_required
@mobile_api_errors
def inbox_merged_document(request, submission_id: int, fmt: str):
    from magicforms.api.mobile_documents import submission_merged_document_mobile

    return submission_merged_document_mobile(request, submission_id, fmt)


@require_GET
@mobile_token_required
@mobile_api_errors
def inbox_document_attachment(request, submission_id: int, attachment_id: int):
    from magicforms.api.mobile_documents import submission_attachment_download_mobile

    return submission_attachment_download_mobile(request, submission_id, attachment_id)


@require_GET
@mobile_token_required
@mobile_api_errors
def inbox_document_attachment_pdf(request, submission_id: int, attachment_id: int):
    from magicforms.api.mobile_documents import submission_attachment_pdf_mobile

    return submission_attachment_pdf_mobile(request, submission_id, attachment_id)
