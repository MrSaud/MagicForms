from django.urls import path, register_converter

from .opaque_ids import OpaqueIdConverter

from . import views
from .outbound import views as outbound_views


class SubmissionRefConverter:
    """Public submission track token: digits only (14 for ``yymmdd`` + minute + 6 random; 16 for older rows)."""

    regex = "[0-9]{14,16}"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return str(value)


register_converter(SubmissionRefConverter, "subref")

app_name = "magicforms"

register_converter(OpaqueIdConverter, "oid")

urlpatterns = [
    path("", views.home, name="home"),
    path("welcome/", views.landing, name="landing"),
    path("account/signatures/", views.my_signatures, name="my_signatures"),
    path("account/signatures/replace/", views.my_signature_replace, name="my_signature_replace"),
    path(
        "account/forms-to-complete/",
        views.pending_related_list,
        name="pending_related",
    ),
    path("account/drafts/", views.my_drafts, name="my_drafts"),
    path(
        "e/<slug:entity_slug>/f/<slug:slug>/related/<uuid:access_token>/",
        views.related_form_public,
        name="related_form_public",
    ),
    path(
        "e/<slug:entity_slug>/f/<slug:slug>/intro-attachment/",
        views.form_intro_attachment,
        name="form_intro_attachment",
    ),
    path(
        "e/<slug:entity_slug>/f/<slug:slug>/intro-qrcode.png",
        views.form_intro_qrcode,
        name="form_intro_qrcode",
    ),
    path(
        "e/<slug:entity_slug>/f/<slug:slug>/",
        views.form_public,
        name="form_public",
    ),
    path(
        "e/<slug:entity_slug>/f/<slug:slug>/s/<subref:token>/document/",
        views.submission_document,
        name="submission_document",
    ),
    path(
        "e/<slug:entity_slug>/f/<slug:slug>/s/<subref:token>/signature/place/",
        views.submission_signature_place,
        name="submission_signature_place",
    ),
    path(
        "e/<slug:entity_slug>/f/<slug:slug>/s/<subref:token>/signature/<oid:placement_id>/remove/",
        views.submission_signature_remove,
        name="submission_signature_remove",
    ),
    path(
        "e/<slug:entity_slug>/f/<slug:slug>/s/<subref:token>/merged/<slug:fmt>/",
        views.submission_merged_document,
        name="submission_merged_document",
    ),
    path(
        "e/<slug:entity_slug>/f/<slug:slug>/s/<subref:token>/attachment/<oid:attachment_id>/pdf/",
        views.submission_attachment_pdf,
        name="submission_attachment_pdf",
    ),
    path(
        "e/<slug:entity_slug>/f/<slug:slug>/s/<subref:token>/",
        views.submission_detail,
        name="submission_detail",
    ),
    path("track/", views.submission_track, name="submission_track"),
    path("e/<slug:entity_slug>/", views.entity_home, name="entity_home"),
    path("f/<slug:slug>/s/<subref:token>/", views.submission_detail_legacy_redirect, name="submission_detail_legacy"),
    path("f/<slug:slug>/", views.form_public_legacy_redirect, name="form_public_legacy"),
    path(
        "outbound/files/download/",
        outbound_views.outbound_file_download,
        name="outbound_file_download",
    ),
]
