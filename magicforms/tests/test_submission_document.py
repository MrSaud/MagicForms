"""Post-submit landing page: filled DOCX template shown as PDF."""

from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.urls import reverse

from magicforms.models import Entity, Form, FormSubmission
from magicforms.views import _post_submit_redirect


class SubmissionDocumentTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org")
        self.form = Form.objects.create(entity=self.entity, title="Leave", slug="leave", is_published=True)
        self.submission = FormSubmission.objects.create(form=self.form)
        self.url = reverse(
            "magicforms:submission_document",
            kwargs={"entity_slug": "org", "slug": "leave", "token": self.submission.reference_token},
        )
        self.detail_url = reverse(
            "magicforms:submission_detail",
            kwargs={"entity_slug": "org", "slug": "leave", "token": self.submission.reference_token},
        )

    def _set_docx_template(self):
        self.form.print_template.name = "print_templates/leave.docx"
        self.form.save(update_fields=["print_template"])

    @patch("magicforms.views.docx_to_pdf_available", return_value=True)
    def test_shows_pdf_viewer_for_docx_template(self, _lo):
        self._set_docx_template()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="mf-doc-viewer"')
        self.assertContains(r, "/merged/pdf/?inline=1")
        self.assertContains(r, self.submission.reference_token)

    def test_redirects_to_tracking_page_without_docx_template(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].endswith(self.detail_url))

    @patch("magicforms.views.docx_to_pdf_available", return_value=False)
    def test_redirects_when_pdf_conversion_unavailable(self, _lo):
        self._set_docx_template()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].endswith(self.detail_url))

    def test_pdf_template_is_not_treated_as_docx(self):
        self.form.print_template.name = "print_templates/leave.pdf"
        self.form.save(update_fields=["print_template"])
        with patch("magicforms.views.docx_to_pdf_available", return_value=True):
            r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)

    @patch("magicforms.views.docx_to_pdf_available", return_value=True)
    def test_post_submit_redirect_targets_document_page(self, _lo):
        self._set_docx_template()
        request = RequestFactory().get("/")
        resp = _post_submit_redirect(request, self.entity, self.form, self.submission)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].endswith(self.url))

    def test_post_submit_redirect_falls_back_to_detail(self):
        request = RequestFactory().get("/")
        resp = _post_submit_redirect(request, self.entity, self.form, self.submission)
        self.assertTrue(resp["Location"].endswith(self.detail_url))
