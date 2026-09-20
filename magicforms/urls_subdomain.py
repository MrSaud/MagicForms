"""Public portal URLs on entity subdomains (``{slug}.example.com``)."""

from django.urls import include, path, register_converter

from . import views
from .urls import SubmissionRefConverter

register_converter(SubmissionRefConverter, "subref")

app_name = "magicforms"

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("", views.entity_home, name="entity_home"),
    path("account/signatures/", views.my_signatures, name="my_signatures"),
    path(
        "account/forms-to-complete/",
        views.pending_related_list,
        name="pending_related",
    ),
    path("account/drafts/", views.my_drafts, name="my_drafts"),
    path(
        "f/<slug:slug>/related/<uuid:access_token>/",
        views.related_form_public,
        name="related_form_public",
    ),
    path(
        "f/<slug:slug>/intro-attachment/",
        views.form_intro_attachment,
        name="form_intro_attachment",
    ),
    path(
        "f/<slug:slug>/intro-qrcode.png",
        views.form_intro_qrcode,
        name="form_intro_qrcode",
    ),
    path("track/", views.submission_track, name="submission_track"),
    path("f/<slug:slug>/", views.form_public, name="form_public"),
    path(
        "f/<slug:slug>/s/<subref:token>/document/",
        views.submission_document,
        name="submission_document",
    ),
    path(
        "f/<slug:slug>/s/<subref:token>/signature/place/",
        views.submission_signature_place,
        name="submission_signature_place",
    ),
    path(
        "f/<slug:slug>/s/<subref:token>/signature/<int:placement_id>/remove/",
        views.submission_signature_remove,
        name="submission_signature_remove",
    ),
    path(
        "f/<slug:slug>/s/<subref:token>/merged/<slug:fmt>/",
        views.submission_merged_document,
        name="submission_merged_document",
    ),
    path(
        "f/<slug:slug>/s/<subref:token>/attachment/<int:attachment_id>/pdf/",
        views.submission_attachment_pdf,
        name="submission_attachment_pdf",
    ),
    path(
        "f/<slug:slug>/s/<subref:token>/",
        views.submission_detail,
        name="submission_detail",
    ),
]
