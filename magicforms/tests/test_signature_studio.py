"""Studio "Read document" panel: staff with responses-write may stamp and remove signatures; readers may not."""

import base64
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from django.core.files.base import ContentFile

from magicforms.manage_views import MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY
from magicforms.models import Entity, EntityMembership, Form, FormSubmission, SubmissionEvent, UserSignature, WorkflowStep

from .test_signature_access import _png_data_url


class StudioSignatureTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.entity = Entity.objects.create(name="Org", slug="org")
        self.form = Form.objects.create(entity=self.entity, title="F", slug="f", is_published=True)
        self.step = WorkflowStep.objects.create(form=self.form, order=0, label="One", slug="one")
        self.step2 = WorkflowStep.objects.create(form=self.form, order=1, label="Two", slug="two")
        self.submission = FormSubmission.objects.create(form=self.form, current_step=self.step)
        self.writer = User.objects.create_user(username="writer", password="x")
        EntityMembership.objects.create(user=self.writer, entity=self.entity, view_responses_write=True)
        # Signing is tied to being able to act on the current step; the writer handles both steps.
        self.step.assigned_users.add(self.writer)
        self.step2.assigned_users.add(self.writer)
        self.reader = User.objects.create_user(username="reader", password="x")
        EntityMembership.objects.create(user=self.reader, entity=self.entity, view_responses_read=True)
        self.place_url = reverse(
            "manage:submission_signature_place", kwargs={"pk": self.form.pk, "submission_id": self.submission.pk}
        )

    def _place(self):
        return self.client.post(
            self.place_url,
            data=json.dumps({"page": 0, "x": 0.4, "y": 0.8, "width": 0.2, "image": _png_data_url()}),
            content_type="application/json",
        )

    def test_writer_can_place_and_remove(self):
        self.client.force_login(self.writer)
        r = self._place()
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["placements"]), 1)
        self.assertEqual(self.submission.signature_placements.count(), 1)
        remove_url = reverse(
            "manage:submission_signature_remove",
            kwargs={"pk": self.form.pk, "submission_id": self.submission.pk, "placement_id": data["placement_id"]},
        )
        r = self.client.post(remove_url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.submission.signature_placements.count(), 0)

    def test_reader_is_locked_out(self):
        self.client.force_login(self.reader)
        r = self._place()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["locked"], "noaction")
        self.assertEqual(self.submission.signature_placements.count(), 0)

    def test_no_action_means_read_only_even_for_superusers(self):
        boss = get_user_model().objects.create_superuser(username="boss", password="x", email="b@x.invalid")
        self.client.force_login(boss)
        session = self.client.session
        session[MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY] = self.entity.pk  # past the organization chooser
        session.save()
        r = self._place()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["locked"], "noaction")
        # Once the workflow is finished nobody can sign, not even the assignee.
        self.client.force_login(self.writer)
        self.submission.workflow_state = FormSubmission.WorkflowState.COMPLETED
        self.submission.save(update_fields=["workflow_state"])
        r = self._place()
        self.assertEqual(r.status_code, 403)

    def test_anonymous_is_redirected(self):
        r = self._place()
        self.assertEqual(r.status_code, 302)

    def test_signature_is_sealed_once_a_decision_follows_it(self):
        self.client.force_login(self.writer)
        first = self._place().json()["placement_id"]
        SubmissionEvent.objects.create(
            submission=self.submission, kind=SubmissionEvent.Kind.STEP_APPROVED, message="approved", created_by=self.writer
        )
        second = self._place().json()["placement_id"]
        remove = lambda pid: self.client.post(
            reverse(
                "manage:submission_signature_remove",
                kwargs={"pk": self.form.pk, "submission_id": self.submission.pk, "placement_id": pid},
            )
        )
        r = remove(first)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["locked"], "decided")
        self.assertEqual(self.submission.signature_placements.count(), 2)
        # The signature added after the decision is still the signer's to undo.
        r = remove(second)
        self.assertEqual(r.status_code, 200)
        locked = {p["id"]: p["locked"] for p in r.json()["placements"]}
        self.assertEqual(locked, {first: True})

    def test_drawing_is_kept_only_when_a_decision_follows(self):
        self.client.force_login(self.writer)
        data = self._place().json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["remember_candidate"], data["placement_id"])
        self.assertFalse(self.writer.signatures.exists())  # placing alone remembers nothing
        detail_url = reverse("manage:submission_manage_detail", kwargs={"pk": self.form.pk, "submission_id": self.submission.pk})
        r = self.client.post(
            detail_url,
            {
                "workflow_decision": "approve",
                "workflow_decision_comment": "",
                "workflow_action_anchor": str(self.step.pk),
                "remember_signature_placement": str(data["placement_id"]),
            },
        )
        self.assertEqual(r.status_code, 302, r.content[:300])
        self.assertEqual(self.writer.signatures.count(), 1)
        # Next placement uses the stored signature; nothing new is remembered.
        r = self.client.post(
            self.place_url,
            data=json.dumps({"page": 0, "x": 0.6, "y": 0.6, "width": 0.2, "saved_signature_id": self.writer.signatures.first().pk}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["remember_candidate"])
        self.assertEqual(self.writer.signatures.count(), 1)

    def test_remember_ignores_other_peoples_placements(self):
        from magicforms.views import remember_signature_from_placement

        self.client.force_login(self.writer)
        pid = self._place().json()["placement_id"]
        other = get_user_model().objects.create_user(username="other2", password="x")
        self.assertFalse(remember_signature_from_placement(other, self.submission, pid))
        self.assertFalse(other.signatures.exists())

    def test_saved_signature_must_belong_to_the_requester(self):
        other = get_user_model().objects.create_user(username="other", password="x")
        png = base64.b64decode(_png_data_url().split(",", 1)[1])
        sig = UserSignature(user=other, label="x")
        sig.image.save("s.png", ContentFile(png), save=True)
        self.client.force_login(self.writer)
        r = self.client.post(
            self.place_url,
            data=json.dumps({"page": 0, "x": 0.5, "y": 0.5, "saved_signature_id": sig.pk}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.submission.signature_placements.count(), 0)

    def test_update_signature_replaces_the_stored_one(self):
        self.client.force_login(self.writer)
        url = reverse("magicforms:my_signature_replace")
        r = self.client.post(url, data=json.dumps({"image": _png_data_url()}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        first_id = r.json()["id"]
        self.assertEqual(self.writer.signatures.count(), 1)
        r = self.client.post(url, data=json.dumps({"image": _png_data_url()}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], first_id)  # replaced in place, not added
        self.assertEqual(self.writer.signatures.count(), 1)
        r = self.client.post(url, data=json.dumps({"image": "nope"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_undo_approve_unseals_the_signature(self):
        self.client.force_login(self.writer)
        pid = self._place().json()["placement_id"]
        SubmissionEvent.objects.create(
            submission=self.submission, kind=SubmissionEvent.Kind.STEP_APPROVED, message="approved", created_by=self.writer
        )
        remove_url = reverse(
            "manage:submission_signature_remove",
            kwargs={"pk": self.form.pk, "submission_id": self.submission.pk, "placement_id": pid},
        )
        self.assertEqual(self.client.post(remove_url).status_code, 403)  # sealed by the approval
        SubmissionEvent.objects.create(
            submission=self.submission, kind=SubmissionEvent.Kind.APPROVE_UNDONE, message="undone", created_by=self.writer
        )
        r = self.client.post(remove_url)
        self.assertEqual(r.status_code, 200, r.content)  # the undo lifts the seal
        self.assertEqual(self.submission.signature_placements.count(), 0)
