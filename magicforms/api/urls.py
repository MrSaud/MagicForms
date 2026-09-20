"""Mobile API URL routes (main site host, no entity slug in path)."""

from django.urls import path

from . import views

app_name = "mobile_api"

urlpatterns = [
    path("auth/login/", views.auth_login, name="auth_login"),
    path("auth/logout/", views.auth_logout, name="auth_logout"),
    path("auth/me/", views.auth_me, name="auth_me"),
    path(
        "auth/directory-entities/",
        views.auth_directory_entities,
        name="auth_directory_entities",
    ),
    path("home/summary/", views.home_summary, name="home_summary"),
    path("forms/published/", views.forms_published, name="forms_published"),
    path("forms/<int:form_id>/intro/", views.form_intro, name="form_intro"),
    path("forms/<int:form_id>/schema/", views.form_schema, name="form_schema"),
    path("forms/<int:form_id>/submit/", views.form_submit, name="form_submit"),
    path("submissions/search/", views.submissions_search, name="submissions_search"),
    path("inbox/", views.inbox_list, name="inbox_list"),
    path("inbox/<int:submission_id>/", views.inbox_detail, name="inbox_detail"),
    path(
        "inbox/<int:submission_id>/workflow/",
        views.inbox_workflow,
        name="inbox_workflow",
    ),
    path(
        "inbox/<int:submission_id>/thread/",
        views.inbox_thread,
        name="inbox_thread",
    ),
    path(
        "inbox/<int:submission_id>/thread/post/",
        views.inbox_thread_post,
        name="inbox_thread_post",
    ),
    path(
        "inbox/<int:submission_id>/values/<int:value_id>/attachment/",
        views.inbox_value_attachment,
        name="inbox_value_attachment",
    ),
    path(
        "inbox/<int:submission_id>/documents/merged/<str:fmt>/",
        views.inbox_merged_document,
        name="inbox_merged_document",
    ),
    path(
        "inbox/<int:submission_id>/documents/attachments/<int:attachment_id>/",
        views.inbox_document_attachment,
        name="inbox_document_attachment",
    ),
    path(
        "inbox/<int:submission_id>/documents/attachments/<int:attachment_id>/pdf/",
        views.inbox_document_attachment_pdf,
        name="inbox_document_attachment_pdf",
    ),
    path("related/pending/", views.related_pending, name="related_pending"),
    path(
        "related/<uuid:access_token>/schema/",
        views.related_form_schema,
        name="related_form_schema",
    ),
    path(
        "related/<uuid:access_token>/submit/",
        views.related_form_submit,
        name="related_form_submit",
    ),
    path("signatures/", views.signatures, name="signatures"),
    path(
        "signatures/<int:signature_id>/image/",
        views.signature_replace_image,
        name="signature_replace_image",
    ),
    path(
        "signatures/<int:signature_id>/primary/",
        views.signature_set_primary,
        name="signature_set_primary",
    ),
    path(
        "signatures/<int:signature_id>/",
        views.signature_delete,
        name="signature_delete",
    ),
    path("devices/register/", views.device_register, name="device_register"),
    path("devices/unregister/", views.device_unregister, name="device_unregister"),
]
