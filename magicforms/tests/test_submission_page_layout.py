"""Studio submission page: answers appear only when the form has no print template."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from magicforms.models import Entity, EntityMembership, FieldType, Form, FormField, FormSubmission, SubmissionValue, WorkflowStep


class SubmissionPageLayoutTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.entity = Entity.objects.create(name="Org", slug="org-layout")
        self.form = Form.objects.create(entity=self.entity, title="Plain", slug="plain")
        self.field = FormField.objects.create(form=self.form, name="name", label="Full name", field_type=FieldType.TEXT, order=0)
        self.step = WorkflowStep.objects.create(form=self.form, order=0, label="One", slug="one")
        self.sub = FormSubmission.objects.create(form=self.form, current_step=self.step)
        SubmissionValue.objects.create(submission=self.sub, field=self.field, value="Sara Ali")
        self.staff = User.objects.create_user(username="staffer", password="x")
        EntityMembership.objects.create(user=self.staff, entity=self.entity, view_responses_read=True)
        self.url = reverse("manage:submission_manage_detail", kwargs={"pk": self.form.pk, "submission_id": self.sub.pk})

    def test_no_template_shows_answers_open_and_no_document_section(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Full name")
        self.assertContains(r, "Sara Ali")
        self.assertNotContains(r, "Read document section")
        self.assertContains(r, 'class="mf-thread-card-details" open')
        self.assertContains(r, "data-mf-side-toggle")
