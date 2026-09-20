from django.contrib.auth.views import LogoutView
from .opaque_ids import OpaqueIdConverter
from django.urls import register_converter, path

from . import (
    activity_log_views,
    manage_views,
    outbound_manage_views,
    submit_validation_manage_views,
    workflow_builder_views,
)
from .studio_login import StudioLoginView

app_name = "manage"

register_converter(OpaqueIdConverter, "oid")

urlpatterns = [
    path(
        "login/",
        StudioLoginView.as_view(),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("choose-organization/", manage_views.choose_organization, name="choose_organization"),
    path("help/", manage_views.studio_help, name="studio_help"),
    path(
        "super/scope/",
        manage_views.superuser_entity_scope,
        name="superuser_entity_scope",
    ),
    path("super/entities/", manage_views.entity_list, name="entity_list"),
    path("super/entities/new/", manage_views.entity_add, name="entity_add"),
    path("super/entities/<oid:pk>/edit/", manage_views.entity_edit, name="entity_edit"),
    path(
        "organizations/<oid:pk>/email-notifications/",
        manage_views.entity_email_notifications,
        name="entity_email_notifications",
    ),
    path(
        "organization/settings/",
        manage_views.organization_settings,
        name="organization_settings",
    ),
    path(
        "organization/<oid:pk>/settings/",
        manage_views.organization_settings_hub,
        name="organization_settings_hub",
    ),
    path(
        "organization/<oid:pk>/settings/general/",
        manage_views.organization_settings_general,
        name="organization_settings_general",
    ),
    path("", manage_views.dashboard, name="dashboard"),
    path("activity-log/", activity_log_views.activity_log_list, name="activity_log_list"),
    path(
        "activity-log/<oid:pk>/",
        activity_log_views.activity_log_detail,
        name="activity_log_detail",
    ),
    path("people/", manage_views.user_list, name="user_list"),
    path("people/new/", manage_views.user_add, name="user_add"),
    path("people/<oid:pk>/edit/", manage_views.user_edit, name="user_edit"),
    path("delegations/", manage_views.delegation_list, name="delegation_list"),
    path("delegations/add/", manage_views.delegation_add, name="delegation_add"),
    path(
        "delegations/<oid:delegation_id>/revoke/",
        manage_views.delegation_revoke,
        name="delegation_revoke",
    ),
    path("api/users/search/", manage_views.user_search, name="user_search"),
    path("inbox/", manage_views.inbox, name="inbox"),
    path("inbox/batch/", manage_views.inbox_batch_action, name="inbox_batch_action"),
    path("inbox/highlight/", manage_views.inbox_highlight, name="inbox_highlight"),
    path("inbox/ai-chat/", manage_views.inbox_ai_chat, name="inbox_ai_chat"),
    path("tasks/", manage_views.task_list, name="task_list"),
    path("submissions/search/", manage_views.submission_search, name="submission_search"),
    path("responses-grid/", manage_views.responses_grid, name="responses_grid"),
    path("responses-grid/export/", manage_views.responses_grid_export, name="responses_grid_export"),
    path(
        "responses-grid/highlight/",
        manage_views.responses_grid_highlight,
        name="responses_grid_highlight",
    ),
    path(
        "responses-grid/bulk-email/",
        manage_views.responses_grid_bulk_email,
        name="responses_grid_bulk_email",
    ),
    path(
        "responses-grid/views/save/",
        manage_views.responses_grid_view_save,
        name="responses_grid_view_save",
    ),
    path(
        "responses-grid/views/<oid:view_pk>/delete/",
        manage_views.responses_grid_view_delete,
        name="responses_grid_view_delete",
    ),
    path(
        "responses-grid/views/<oid:view_pk>/share/",
        manage_views.responses_grid_view_share,
        name="responses_grid_view_share",
    ),
    path("categories/", manage_views.category_list, name="category_list"),
    path("categories/add/", manage_views.category_add, name="category_add"),
    path("forms/new/", manage_views.form_create, name="form_create"),
    path(
        "forms/generate-from-text/",
        manage_views.form_generate_from_text,
        name="form_generate_from_text",
    ),
    path(
        "forms/<oid:pk>/archive/",
        manage_views.form_soft_delete,
        name="form_archive",
    ),
    path(
        "forms/<oid:pk>/restore/",
        manage_views.form_restore,
        name="form_restore",
    ),
    path(
        "forms/<oid:pk>/duplicate/",
        manage_views.form_duplicate,
        name="form_duplicate",
    ),
    path("forms/<oid:pk>/", manage_views.form_detail, name="form_detail"),
    path(
        "forms/<oid:pk>/claim-sample/",
        manage_views.sample_form_claim,
        name="sample_form_claim",
    ),
    path(
        "forms/<oid:pk>/preview/",
        manage_views.form_preview,
        name="form_preview",
    ),
    path(
        "forms/<oid:pk>/share-key/",
        manage_views.form_share_key_action,
        name="form_share_key_action",
    ),
    path(
        "forms/<oid:pk>/qrcode/image/",
        manage_views.form_qrcode_image,
        name="form_qrcode_image",
    ),
    path("forms/<oid:pk>/qrcode/", manage_views.form_qrcode, name="form_qrcode"),
    path(
        "forms/<oid:pk>/print-template/download/",
        manage_views.form_print_template_download,
        name="form_print_template_download",
    ),
    path(
        "forms/<oid:pk>/print-template-odt/download/",
        manage_views.form_print_template_odt_download,
        name="form_print_template_odt_download",
    ),
    path("forms/<oid:pk>/edit/", manage_views.form_edit, name="form_edit"),
    path(
        "forms/<oid:pk>/intro/",
        manage_views.form_intro_edit,
        name="form_intro_edit",
    ),
    path(
        "forms/<oid:pk>/intro/preview/",
        manage_views.form_intro_preview,
        name="form_intro_preview",
    ),
    path(
        "forms/<oid:pk>/intro/slides/add/",
        manage_views.intro_slide_add,
        name="intro_slide_add",
    ),
    path(
        "forms/<oid:pk>/intro/slides/<oid:slide_id>/delete/",
        manage_views.intro_slide_delete,
        name="intro_slide_delete",
    ),
    path(
        "forms/<oid:pk>/intro/slides/reorder/",
        manage_views.intro_slide_reorder,
        name="intro_slide_reorder",
    ),
    path(
        "forms/<oid:pk>/submit-validation/",
        submit_validation_manage_views.form_submit_validation,
        name="form_submit_validation",
    ),
    path(
        "forms/<oid:pk>/submit-validation/test/",
        submit_validation_manage_views.form_submit_validation_test,
        name="form_submit_validation_test",
    ),
    path("forms/<oid:pk>/outbound/", outbound_manage_views.form_outbound, name="form_outbound"),
    path(
        "forms/<oid:pk>/outbound/test/custom/",
        outbound_manage_views.form_outbound_test_custom,
        name="form_outbound_test_custom",
    ),
    path(
        "forms/<oid:pk>/outbound/test/health/",
        outbound_manage_views.form_outbound_test_health,
        name="form_outbound_test_health",
    ),
    path(
        "forms/<oid:pk>/outbound/test/sample/",
        outbound_manage_views.form_outbound_test_sample,
        name="form_outbound_test_sample",
    ),
    path(
        "forms/<oid:pk>/outbound/test/submission/",
        outbound_manage_views.form_outbound_test_submission,
        name="form_outbound_test_submission",
    ),
    path(
        "forms/<oid:pk>/outbound/deliveries/<oid:delivery_id>/retry/",
        outbound_manage_views.form_outbound_retry,
        name="form_outbound_retry",
    ),
    path(
        "forms/<oid:pk>/related/",
        manage_views.related_link_list,
        name="related_link_list",
    ),
    path(
        "forms/<oid:pk>/related/add/",
        manage_views.related_link_add,
        name="related_link_add",
    ),
    path(
        "forms/<oid:pk>/related/<oid:link_id>/delete/",
        manage_views.related_link_delete,
        name="related_link_delete",
    ),
    path("forms/<oid:pk>/logos/", manage_views.logo_list, name="logo_list"),
    path("forms/<oid:pk>/logos/add/", manage_views.logo_add, name="logo_add"),
    path(
        "forms/<oid:pk>/logos/<oid:logo_id>/edit/",
        manage_views.logo_edit,
        name="logo_edit",
    ),
    path(
        "forms/<oid:pk>/logos/<oid:logo_id>/delete/",
        manage_views.logo_delete,
        name="logo_delete",
    ),
    path("forms/<oid:pk>/sections/", manage_views.section_list, name="section_list"),
    path(
        "forms/<oid:pk>/sections/reorder/",
        manage_views.section_reorder,
        name="section_reorder",
    ),
    path("forms/<oid:pk>/sections/add/", manage_views.section_add, name="section_add"),
    path(
        "forms/<oid:pk>/sections/<oid:section_id>/edit/",
        manage_views.section_edit,
        name="section_edit",
    ),
    path(
        "forms/<oid:pk>/sections/<oid:section_id>/delete/",
        manage_views.section_delete,
        name="section_delete",
    ),
    path("forms/<oid:pk>/fields/", manage_views.field_list, name="field_list"),
    path("forms/<oid:pk>/fields/reorder/", manage_views.field_reorder, name="field_reorder"),
    path("forms/<oid:pk>/fields/add/", manage_views.field_add, name="field_add"),
    path(
        "forms/<oid:pk>/fields/<oid:field_id>/edit/",
        manage_views.field_edit,
        name="field_edit",
    ),
    path(
        "forms/<oid:pk>/fields/<oid:field_id>/duplicate/",
        manage_views.field_duplicate,
        name="field_duplicate",
    ),
    path(
        "forms/<oid:pk>/fields/<oid:field_id>/delete/",
        manage_views.field_delete,
        name="field_delete",
    ),
    path("forms/<oid:pk>/workflow/", workflow_builder_views.workflow_builder_page, name="workflow_list"),
    path(
        "forms/<oid:pk>/workflow/api/state/",
        workflow_builder_views.workflow_builder_state,
        name="workflow_builder_state",
    ),
    path(
        "forms/<oid:pk>/workflow/api/save/",
        workflow_builder_views.workflow_builder_save,
        name="workflow_builder_save",
    ),
    path(
        "forms/<oid:pk>/workflow/api/<oid:step_id>/delete/",
        workflow_builder_views.workflow_builder_delete,
        name="workflow_builder_delete",
    ),
    path(
        "forms/<oid:pk>/workflow/reorder/",
        manage_views.workflow_reorder,
        name="workflow_reorder",
    ),
    path("forms/<oid:pk>/workflow/add/", manage_views.workflow_add, name="workflow_add"),
    path(
        "forms/<oid:pk>/workflow/<oid:step_id>/edit/",
        manage_views.workflow_edit,
        name="workflow_edit",
    ),
    path(
        "forms/<oid:pk>/workflow/<oid:step_id>/delete/",
        manage_views.workflow_delete,
        name="workflow_delete",
    ),
    path(
        "forms/<oid:pk>/submissions/",
        manage_views.submission_list,
        name="submission_list",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/timeline/",
        manage_views.submission_timeline,
        name="submission_timeline",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/timeline/share/",
        manage_views.submission_timeline_share,
        name="submission_timeline_share",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/timeline/dismiss/",
        manage_views.submission_timeline_dismiss,
        name="submission_timeline_dismiss",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/timeline.pdf/",
        manage_views.submission_timeline_pdf,
        name="submission_timeline_pdf",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/thread/messages/",
        manage_views.submission_thread_messages_poll,
        name="submission_thread_messages_poll",
    ),
    path(
        "forms/<oid:form_pk>/submissions/<oid:submission_id>/task/",
        manage_views.submission_task_action,
        name="submission_task",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/",
        manage_views.submission_manage_detail,
        name="submission_manage_detail",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/document/view/",
        manage_views.submission_document_view,
        name="submission_document_view",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/document/<slug:fmt>/",
        manage_views.submission_merge_document,
        name="submission_merge_document",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/signature/place/",
        manage_views.submission_signature_place,
        name="submission_signature_place",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/signature/<oid:placement_id>/remove/",
        manage_views.submission_signature_remove,
        name="submission_signature_remove",
    ),
    path(
        "forms/<oid:pk>/submissions/<oid:submission_id>/attachments/<oid:attachment_id>/pdf/",
        manage_views.submission_attachment_pdf,
        name="submission_attachment_pdf",
    ),
]
