"""
Schema and per-form toggle for workflow routing (Form.routing_mode, FormSubmission.current_holder).

Dynamic routing is not implemented yet: these tests lock in that every existing form keeps its
current fixed-step behaviour untouched, that the toggle is editable only while nothing is mid-flight,
and that a form an admin switches to dynamic pauses approve/reject with a clear message rather than
running the old fixed-step logic against steps that are no longer wired as a pipeline.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from magicforms.manage_views import _apply_inbox_workflow_decision
from magicforms.models import Entity, EntityMembership, Form, FormSubmission, WorkflowStep
from magicforms.staff_forms import StaffMetaForm
from magicforms.workflow_access import form_supports_workflow_decisions
from magicforms.workflow_decision import perform_workflow_decision


class RoutingModeDefaultsTests(TestCase):
    def test_new_forms_default_to_fixed_steps(self):
        entity = Entity.objects.create(name="Org", slug="org-routing-default")
        form = Form.objects.create(entity=entity, title="F", slug="f-routing-default")
        self.assertEqual(form.routing_mode, Form.RoutingMode.FIXED_STEPS)
        self.assertFalse(form.uses_dynamic_routing)
        self.assertTrue(form_supports_workflow_decisions(form))

    def test_dynamic_mode_is_reported_correctly(self):
        entity = Entity.objects.create(name="Org", slug="org-routing-dynamic")
        form = Form.objects.create(
            entity=entity, title="F", slug="f-routing-dynamic", routing_mode=Form.RoutingMode.DYNAMIC
        )
        self.assertTrue(form.uses_dynamic_routing)
        self.assertFalse(form_supports_workflow_decisions(form))


class RoutingModeToggleFormTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-routing-toggle")
        self.form = Form.objects.create(entity=self.entity, title="F", slug="f-routing-toggle")
        self.step = WorkflowStep.objects.create(form=self.form, order=0, label="One", slug="one")
        self.user = get_user_model().objects.create_superuser(
            username="boss", password="x", email="boss@x.invalid"
        )

    def _form_data(self, **overrides):
        data = {
            "entity": self.entity.pk,
            "title": self.form.title,
            "description": "",
            "layout_direction": Form.LayoutDirection.AUTO,
            "one_time_submit": "",
            "is_for_public": "on",
            "allow_submission_forward": "",
            "routing_mode": Form.RoutingMode.DYNAMIC,
            "hide_from_form_lists": "",
        }
        data.update(overrides)
        return data

    def test_switching_routing_mode_is_blocked_while_a_submission_is_in_progress(self):
        FormSubmission.objects.create(form=self.form, current_step=self.step)
        f = StaffMetaForm(
            self._form_data(), instance=self.form, staff_user=self.user, request=None
        )
        self.assertFalse(f.is_valid())
        self.assertIn("routing_mode", f.errors)
        self.form.refresh_from_db()
        self.assertEqual(self.form.routing_mode, Form.RoutingMode.FIXED_STEPS)

    def test_switching_routing_mode_is_allowed_with_nothing_in_progress(self):
        FormSubmission.objects.create(
            form=self.form, current_step=None, workflow_state=FormSubmission.WorkflowState.COMPLETED
        )
        f = StaffMetaForm(
            self._form_data(), instance=self.form, staff_user=self.user, request=None
        )
        self.assertTrue(f.is_valid(), f.errors)
        saved = f.save()
        self.assertEqual(saved.routing_mode, Form.RoutingMode.DYNAMIC)

    def test_unrelated_field_edits_do_not_trip_the_guard(self):
        FormSubmission.objects.create(form=self.form, current_step=self.step)
        f = StaffMetaForm(
            self._form_data(routing_mode=Form.RoutingMode.FIXED_STEPS, title="Renamed"),
            instance=self.form,
            staff_user=self.user,
            request=None,
        )
        self.assertTrue(f.is_valid(), f.errors)


class DynamicRoutingPausesDecisionsTests(TestCase):
    """Every existing decision entry point refuses cleanly on a dynamic-mode form; fixed-step forms are untouched."""

    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-routing-decisions")
        self.dynamic_form = Form.objects.create(
            entity=self.entity,
            title="Dynamic",
            slug="dyn",
            routing_mode=Form.RoutingMode.DYNAMIC,
        )
        self.dyn_step = WorkflowStep.objects.create(form=self.dynamic_form, order=0, label="One", slug="one")
        self.actor = get_user_model().objects.create_user(username="actor", password="x")
        self.dyn_step.assigned_users.add(self.actor)
        EntityMembership.objects.create(user=self.actor, entity=self.entity, view_responses_write=True)
        self.dyn_sub = FormSubmission.objects.create(form=self.dynamic_form, current_step=self.dyn_step)

        self.fixed_form = Form.objects.create(entity=self.entity, title="Fixed", slug="fixed")
        self.fixed_step = WorkflowStep.objects.create(form=self.fixed_form, order=0, label="One", slug="one")
        self.fixed_step.assigned_users.add(self.actor)
        self.fixed_sub = FormSubmission.objects.create(form=self.fixed_form, current_step=self.fixed_step)

    def test_shared_decision_engine_refuses_on_dynamic_form(self):
        ok, err, result = perform_workflow_decision(
            user=self.actor, submission=self.dyn_sub, decision="approve"
        )
        self.assertFalse(ok)
        self.assertIn("Dynamic routing", err)
        self.assertIsNone(result)
        self.dyn_sub.refresh_from_db()
        self.assertEqual(self.dyn_sub.current_step_id, self.dyn_step.pk)

    def test_shared_decision_engine_still_works_on_a_fixed_step_form(self):
        ok, err, result = perform_workflow_decision(
            user=self.actor, submission=self.fixed_sub, decision="approve"
        )
        self.assertTrue(ok, err)
        self.assertEqual(result["outcome"], "completed")

    def test_inbox_quick_decision_skips_dynamic_form(self):
        outcome = _apply_inbox_workflow_decision(
            _FakeRequest(self.actor), self.dyn_sub, "approve", ""
        )
        self.assertIsNone(outcome)
        self.dyn_sub.refresh_from_db()
        self.assertEqual(self.dyn_sub.current_step_id, self.dyn_step.pk)

    def test_studio_detail_page_shows_the_pending_message_for_dynamic_forms(self):
        self.client.force_login(self.actor)
        url = reverse(
            "manage:submission_manage_detail",
            kwargs={"pk": self.dynamic_form.pk, "submission_id": self.dyn_sub.pk},
        )
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'name="workflow_decision" value="approve"')
        self.assertContains(r, "still being rolled out")

    def test_studio_detail_page_post_is_refused_for_dynamic_forms(self):
        self.client.force_login(self.actor)
        url = reverse(
            "manage:submission_manage_detail",
            kwargs={"pk": self.dynamic_form.pk, "submission_id": self.dyn_sub.pk},
        )
        r = self.client.post(
            url,
            {
                "workflow_decision": "approve",
                "workflow_decision_comment": "",
                "workflow_action_anchor": str(self.dyn_step.pk),
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.dyn_sub.refresh_from_db()
        self.assertEqual(self.dyn_sub.current_step_id, self.dyn_step.pk)

    def test_studio_detail_page_still_shows_actions_for_fixed_step_forms(self):
        self.client.force_login(self.actor)
        url = reverse(
            "manage:submission_manage_detail",
            kwargs={"pk": self.fixed_form.pk, "submission_id": self.fixed_sub.pk},
        )
        r = self.client.get(url)
        self.assertContains(r, 'name="workflow_decision" value="approve"')


class _FakeRequest:
    """Minimal stand-in for the bits ``_apply_inbox_workflow_decision`` reads off ``request``."""

    def __init__(self, user):
        self.user = user
