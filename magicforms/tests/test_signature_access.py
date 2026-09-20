"""Who may add or remove signatures on the post-submit document page."""

import base64
import io
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from magicforms.models import Entity, Form, FormSubmission, WorkflowStep
from magicforms.views import _SIGN_SESSION_KEY


def _png_data_url() -> str:
    from PIL import Image, ImageDraw

    im = Image.new("RGBA", (200, 80), (0, 0, 0, 0))
    ImageDraw.Draw(im).line([(10, 60), (100, 10), (190, 60)], fill=(0, 0, 0, 255), width=4)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class SignatureAccessTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org")
        self.form = Form.objects.create(entity=self.entity, title="F", slug="f", is_published=True, is_for_public=True)
        self.step1 = WorkflowStep.objects.create(form=self.form, order=0, label="One", slug="one")
        self.step2 = WorkflowStep.objects.create(form=self.form, order=1, label="Two", slug="two")
        self.submission = FormSubmission.objects.create(form=self.form, current_step=self.step1)
        self.user = get_user_model().objects.create_user(username="u", password="x")
        self.place_url = reverse(
            "magicforms:submission_signature_place",
            kwargs={"entity_slug": "org", "slug": "f", "token": self.submission.reference_token},
        )
        self.doc_url = reverse(
            "magicforms:submission_document",
            kwargs={"entity_slug": "org", "slug": "f", "token": self.submission.reference_token},
        )

    def _place(self):
        return self.client.post(
            self.place_url,
            data=json.dumps({"page": 0, "x": 0.5, "y": 0.5, "width": 0.2, "image": _png_data_url()}),
            content_type="application/json",
        )

    def _grant_session(self):
        session = self.client.session
        session[_SIGN_SESSION_KEY] = [self.submission.reference_token]
        session.save()

    def test_public_form_forwarded_link_is_view_only(self):
        r = self._place()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["locked"], "identity")

    def test_public_form_submitting_session_may_sign(self):
        self._grant_session()
        r = self._place()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.submission.signature_placements.count(), 1)

    def test_locked_once_submission_leaves_first_step(self):
        self._grant_session()
        FormSubmission.objects.filter(pk=self.submission.pk).update(current_step=self.step2)
        r = self._place()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["locked"], "workflow")

    def test_locked_once_completed_or_rejected(self):
        self._grant_session()
        for state in (FormSubmission.WorkflowState.COMPLETED, FormSubmission.WorkflowState.REJECTED):
            FormSubmission.objects.filter(pk=self.submission.pk).update(workflow_state=state)
            self.assertEqual(self._place().status_code, 403)

    def test_signin_form_requires_the_submitting_account(self):
        Form.objects.filter(pk=self.form.pk).update(is_for_public=False)
        FormSubmission.objects.filter(pk=self.submission.pk).update(submitted_by=self.user)
        self._grant_session()  # session alone is not enough for sign-in forms
        self.assertEqual(self._place().status_code, 403)

        other = get_user_model().objects.create_user(username="other", password="x")
        self.client.force_login(other)
        self.assertEqual(self._place().status_code, 403)

        self.client.force_login(self.user)
        self.assertEqual(self._place().status_code, 200)

    def test_document_page_reports_lock_state(self):
        from unittest.mock import patch

        self.form.print_template.name = "print_templates/f.docx"
        self.form.save(update_fields=["print_template"])
        with patch("magicforms.views.docx_to_pdf_available", return_value=True):
            r = self.client.get(self.doc_url)
            self.assertContains(r, 'data-can-sign="0"')
            self.assertContains(r, "view-only")
            self._grant_session()
            r = self.client.get(self.doc_url)
            self.assertContains(r, 'data-can-sign="1"')
