"""Visual workflow builder JSON API (studio → form → Workflow)."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from magicforms.models import Entity, EntityMembership, Form, FormSubmission, WorkflowStep


class WorkflowBuilderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.entity = Entity.objects.create(name="Org", slug="org")
        self.other_entity = Entity.objects.create(name="Other", slug="other")
        self.staff = User.objects.create_user(username="staff", password="x", is_staff=True)
        self.member = User.objects.create_user(username="member", password="x")
        self.outsider = User.objects.create_user(username="outsider", password="x")
        self.reader = User.objects.create_user(username="reader", password="x")
        EntityMembership.objects.create(user=self.staff, entity=self.entity)
        EntityMembership.objects.create(user=self.member, entity=self.entity)
        EntityMembership.objects.create(user=self.outsider, entity=self.other_entity)
        EntityMembership.objects.create(user=self.reader, entity=self.entity, manage_forms_read=True)
        self.form = Form.objects.create(entity=self.entity, title="Leave", slug="leave")
        self.client.force_login(self.staff)

    def _post(self, name, payload, **kwargs):
        return self.client.post(
            reverse(name, kwargs=kwargs),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _save(self, payload):
        return self._post("manage:workflow_builder_save", payload, pk=self.form.pk)

    def test_page_renders_builder_with_state(self):
        WorkflowStep.objects.create(form=self.form, order=0, label="Head", slug="head")
        r = self.client.get(reverse("manage:workflow_list", kwargs={"pk": self.form.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="mf-wfb-state"')
        self.assertContains(r, "workflow_builder.js")
        self.assertContains(r, "Head")

    def test_create_appends_and_assigns_members(self):
        r = self._save({"label": "Head", "assignee_ids": [self.member.pk], "insert_after": None})
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertTrue(data["ok"])
        step = WorkflowStep.objects.get(pk=data["step_id"])
        self.assertEqual(step.order, 0)
        self.assertTrue(step.slug)
        self.assertEqual(list(step.assigned_users.all()), [self.member])
        self.assertEqual([s["label"] for s in data["state"]["steps"]], ["Head"])
        self.assertEqual(data["state"]["steps"][0]["assignees"][0]["id"], self.member.pk)

    def test_insert_positions(self):
        a = WorkflowStep.objects.create(form=self.form, order=0, label="A", slug="a")
        WorkflowStep.objects.create(form=self.form, order=1, label="C", slug="c")

        r = self._save({"label": "B", "insert_after": a.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([s["label"] for s in r.json()["state"]["steps"]], ["A", "B", "C"])

        r = self._save({"label": "Start", "insert_after": "start"})
        self.assertEqual([s["label"] for s in r.json()["state"]["steps"]], ["Start", "A", "B", "C"])

        r = self._save({"label": "Last"})
        self.assertEqual(
            [s["label"] for s in r.json()["state"]["steps"]], ["Start", "A", "B", "C", "Last"]
        )
        orders = list(self.form.workflow_steps.order_by("order").values_list("order", flat=True))
        self.assertEqual(orders, [0, 1, 2, 3, 4])

    def test_update_keeps_position_and_replaces_assignees(self):
        a = WorkflowStep.objects.create(form=self.form, order=0, label="A", slug="a")
        b = WorkflowStep.objects.create(form=self.form, order=1, label="B", slug="b")
        a.assigned_users.add(self.member)
        r = self._save({"id": a.pk, "label": "A2", "description": "desc", "assignee_ids": [self.staff.pk]})
        self.assertEqual(r.status_code, 200, r.content)
        a.refresh_from_db()
        self.assertEqual((a.label, a.description, a.order), ("A2", "desc", 0))
        self.assertEqual(list(a.assigned_users.all()), [self.staff])
        self.assertEqual([s["id"] for s in r.json()["state"]["steps"]], [a.pk, b.pk])

    def test_validation_errors(self):
        r = self._save({"label": "   "})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["field"], "label")

        r = self._save({"label": "X", "assignee_ids": [self.outsider.pk]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["field"], "assignees")
        self.assertFalse(WorkflowStep.objects.filter(form=self.form).exists())

        r = self._save({"label": "X", "insert_after": 999999})
        self.assertEqual(r.status_code, 400)

        r = self.client.post(
            reverse("manage:workflow_builder_save", kwargs={"pk": self.form.pk}),
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_delete_reindexes_and_unpublishes_when_empty(self):
        a = WorkflowStep.objects.create(form=self.form, order=0, label="A", slug="a")
        b = WorkflowStep.objects.create(form=self.form, order=1, label="B", slug="b")
        r = self._post("manage:workflow_builder_delete", {}, pk=self.form.pk, step_id=a.pk)
        self.assertEqual(r.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.order, 0)
        self.assertEqual([s["id"] for s in r.json()["state"]["steps"]], [b.pk])

    def test_delete_protected_when_submissions_reference_step(self):
        a = WorkflowStep.objects.create(form=self.form, order=0, label="A", slug="a")
        FormSubmission.objects.create(form=self.form, current_step=a)
        r = self._post("manage:workflow_builder_delete", {}, pk=self.form.pk, step_id=a.pk)
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.json()["ok"])
        self.assertTrue(WorkflowStep.objects.filter(pk=a.pk).exists())
        self.assertEqual(r.json()["state"]["steps"][0]["submissions_count"], 1)

    def test_state_endpoint(self):
        WorkflowStep.objects.create(form=self.form, order=0, label="A", slug="a")
        r = self.client.get(reverse("manage:workflow_builder_state", kwargs={"pk": self.form.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["state"]["steps"][0]["label"], "A")

    def test_read_only_member_cannot_write(self):
        self.client.force_login(self.reader)
        r = self._save({"label": "X"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(WorkflowStep.objects.filter(form=self.form).exists())

    def test_other_org_form_is_404(self):
        other_form = Form.objects.create(entity=self.other_entity, title="O", slug="o")
        r = self._post("manage:workflow_builder_save", {"label": "X"}, pk=other_form.pk)
        self.assertEqual(r.status_code, 404)
