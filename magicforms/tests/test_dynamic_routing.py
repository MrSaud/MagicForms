"""
Dynamic routing engine (Phase 2): route to one chosen person, mark complete, or reject back to
the original submitter; job-title search; the inbox shows unclaimed items and items held by you.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from magicforms.entity_access import entity_users_for_entity_search
from magicforms.manage_views import _maybe_unpublish, _staff_may_sign_document
from magicforms.models import (
    EmployeeProfile,
    Entity,
    EntityMembership,
    FieldType,
    Form,
    FormField,
    FormSubmission,
    SubmissionEvent,
    WorkflowDelegation,
    WorkflowStep,
)
from magicforms.staff_forms import StaffSubmissionRouteForm
from magicforms.workflow_access import inbox_submissions_filter_q, user_may_act_on_submission_workflow
from magicforms.workflow_decision import perform_dynamic_route_decision


def _dynamic_form(entity, slug="dyn"):
    return Form.objects.create(entity=entity, title="Dynamic", slug=slug, routing_mode=Form.RoutingMode.DYNAMIC)


class JobTitleSearchTests(TestCase):
    def test_search_matches_job_title_and_department(self):
        entity = Entity.objects.create(name="Org", slug="org-jt")
        User = get_user_model()
        finn = User.objects.create_user(username="finn", password="x", first_name="Finn")
        EntityMembership.objects.create(user=finn, entity=entity)
        EmployeeProfile.objects.update_or_create(
            user=finn, defaults={"job_title": "Finance Manager", "department": "Finance"}
        )
        other = User.objects.create_user(username="other", password="x")
        EntityMembership.objects.create(user=other, entity=entity)

        by_title = list(entity_users_for_entity_search(entity.pk, "Finance Manager"))
        self.assertIn(finn, by_title)
        self.assertNotIn(other, by_title)

        by_dept = list(entity_users_for_entity_search(entity.pk, "Finance"))
        self.assertIn(finn, by_dept)


class RouteFormValidationTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-route-form")
        User = get_user_model()
        self.actor = User.objects.create_user(username="actor3", password="x")
        self.target = User.objects.create_user(username="target3", password="x")
        EntityMembership.objects.create(user=self.actor, entity=self.entity)
        EntityMembership.objects.create(user=self.target, entity=self.entity)

    def _form(self, **data):
        base = {"action": "route", "target_user": "", "stage_label": "", "comment": ""}
        base.update(data)
        return StaffSubmissionRouteForm(
            base, actor=self.actor, form_entity_id=self.entity.pk, search_url="/x/"
        )

    def test_route_without_a_target_is_invalid(self):
        f = self._form(action="route")
        self.assertFalse(f.is_valid())
        self.assertIn("target_user", f.errors)

    def test_route_with_a_target_is_valid(self):
        f = self._form(action="route", target_user=self.target.pk)
        self.assertTrue(f.is_valid(), f.errors)

    def test_complete_needs_no_target_or_comment(self):
        f = self._form(action="complete")
        self.assertTrue(f.is_valid(), f.errors)

    def test_reject_without_a_comment_is_invalid(self):
        f = self._form(action="reject")
        self.assertFalse(f.is_valid())
        self.assertIn("comment", f.errors)

    def test_target_user_queryset_excludes_the_actor(self):
        f = self._form()
        self.assertNotIn(self.actor, f.fields["target_user"].queryset)
        self.assertIn(self.target, f.fields["target_user"].queryset)


class DynamicRouteEngineTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-route")
        self.form = _dynamic_form(self.entity)
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice", password="x")
        self.bob = User.objects.create_user(username="bob", password="x")
        self.carol = User.objects.create_user(username="carol", password="x")
        for u in (self.alice, self.bob, self.carol):
            EntityMembership.objects.create(user=u, entity=self.entity)
        self.outsider = User.objects.create_user(username="outsider", password="x")  # no membership
        self.submission = FormSubmission.objects.create(form=self.form)  # freshly submitted, unclaimed

    def test_unclaimed_submission_may_be_routed_by_any_org_member(self):
        self.assertIsNone(self.submission.current_holder_id)
        ok, err, result = perform_dynamic_route_decision(
            user=self.alice, submission=self.submission, action="route", target_user_id=self.bob.pk
        )
        self.assertTrue(ok, err)
        self.assertEqual(result["outcome"], "routed")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.current_holder_id, self.bob.pk)
        self.assertEqual(self.submission.workflow_state, FormSubmission.WorkflowState.IN_PROGRESS)
        last_event = self.submission.events.order_by("-pk").first()
        self.assertEqual(last_event.kind, SubmissionEvent.Kind.ROUTED)
        self.assertIn("bob", last_event.message.lower())

    def test_only_the_current_holder_may_act_once_claimed(self):
        self.submission.current_holder = self.bob
        self.submission.save(update_fields=["current_holder"])
        ok, err, result = perform_dynamic_route_decision(
            user=self.alice, submission=self.submission, action="complete"
        )
        self.assertFalse(ok)
        self.assertIsNone(result)
        ok2, err2, result2 = perform_dynamic_route_decision(
            user=self.bob, submission=self.submission, action="complete"
        )
        self.assertTrue(ok2, err2)
        self.assertEqual(result2["outcome"], "completed")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.workflow_state, FormSubmission.WorkflowState.COMPLETED)
        self.assertIsNone(self.submission.current_holder_id)

    def test_reject_stops_the_flow_and_clears_the_holder(self):
        self.submission.current_holder = self.bob
        self.submission.save(update_fields=["current_holder"])
        ok, err, result = perform_dynamic_route_decision(
            user=self.bob, submission=self.submission, action="reject", comment="Missing signature."
        )
        self.assertTrue(ok, err)
        self.assertEqual(result["outcome"], "rejected")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.workflow_state, FormSubmission.WorkflowState.REJECTED)
        self.assertIsNone(self.submission.current_holder_id)

    def test_reject_without_a_reason_is_refused(self):
        ok, err, result = perform_dynamic_route_decision(
            user=self.alice, submission=self.submission, action="reject", comment=""
        )
        self.assertFalse(ok)
        self.assertIn("reason", err)

    def test_route_requires_a_target(self):
        ok, err, result = perform_dynamic_route_decision(
            user=self.alice, submission=self.submission, action="route", target_user_id=None
        )
        self.assertFalse(ok)

    def test_cannot_route_to_self(self):
        ok, err, result = perform_dynamic_route_decision(
            user=self.alice, submission=self.submission, action="route", target_user_id=self.alice.pk
        )
        self.assertFalse(ok)
        self.assertIn("yourself", err)

    def test_cannot_route_to_someone_outside_the_organization(self):
        ok, err, result = perform_dynamic_route_decision(
            user=self.alice, submission=self.submission, action="route", target_user_id=self.outsider.pk
        )
        self.assertFalse(ok)
        self.assertIn("organization", err)

    def test_fixed_step_form_refuses_the_dynamic_engine(self):
        fixed = Form.objects.create(entity=self.entity, title="Fixed", slug="fixed-refuse")
        sub = FormSubmission.objects.create(form=fixed)
        ok, err, result = perform_dynamic_route_decision(
            user=self.alice, submission=sub, action="complete"
        )
        self.assertFalse(ok)
        self.assertIn("fixed", err.lower())

    def test_stage_label_is_recorded_and_cleared_on_complete(self):
        perform_dynamic_route_decision(
            user=self.alice,
            submission=self.submission,
            action="route",
            target_user_id=self.bob.pk,
            stage_label="Finance review",
        )
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.current_stage_label, "Finance review")
        perform_dynamic_route_decision(user=self.bob, submission=self.submission, action="complete")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.current_stage_label, "")

    def test_delegate_may_act_for_the_current_holder(self):
        self.submission.current_holder = self.bob
        self.submission.save(update_fields=["current_holder"])
        WorkflowDelegation.objects.create(entity=self.entity, delegator=self.bob, delegate=self.carol)
        self.assertTrue(user_may_act_on_submission_workflow(self.carol, self.submission))
        ok, err, result = perform_dynamic_route_decision(
            user=self.carol, submission=self.submission, action="complete"
        )
        self.assertTrue(ok, err)


class InboxVisibilityTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-inbox-dyn")
        self.form = _dynamic_form(self.entity, slug="dyn-inbox")
        User = get_user_model()
        self.member = User.objects.create_user(username="member", password="x")
        EntityMembership.objects.create(user=self.member, entity=self.entity)
        self.outsider = User.objects.create_user(username="outsider2", password="x")

    def test_unclaimed_submission_is_visible_to_org_members_not_outsiders(self):
        sub = FormSubmission.objects.create(form=self.form)
        q = inbox_submissions_filter_q(self.member, [self.entity.pk])
        self.assertTrue(FormSubmission.objects.filter(q, pk=sub.pk).exists())
        q_out = inbox_submissions_filter_q(self.outsider, [])
        self.assertFalse(FormSubmission.objects.filter(q_out, pk=sub.pk).exists())

    def test_held_submission_is_visible_only_to_its_holder(self):
        sub = FormSubmission.objects.create(form=self.form, current_holder=self.member)
        q = inbox_submissions_filter_q(self.member, [self.entity.pk])
        self.assertTrue(FormSubmission.objects.filter(q, pk=sub.pk).exists())
        other = get_user_model().objects.create_user(username="member2", password="x")
        EntityMembership.objects.create(user=other, entity=self.entity)
        q_other = inbox_submissions_filter_q(other, [self.entity.pk])
        self.assertFalse(FormSubmission.objects.filter(q_other, pk=sub.pk).exists())


class DynamicRouteStudioViewTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-route-view")
        self.form = _dynamic_form(self.entity, slug="dyn-view")
        User = get_user_model()
        self.alice = User.objects.create_user(username="alicev", password="x")
        self.bob = User.objects.create_user(username="bobv", password="x")
        for u in (self.alice, self.bob):
            EntityMembership.objects.create(user=u, entity=self.entity, view_responses_write=True)
        self.submission = FormSubmission.objects.create(form=self.form)
        self.url = reverse(
            "manage:submission_manage_detail", kwargs={"pk": self.form.pk, "submission_id": self.submission.pk}
        )

    def test_unclaimed_submission_shows_the_route_form(self):
        self.client.force_login(self.alice)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="workflow_dynamic_route_submit"')
        self.assertContains(r, 'value="route"')
        self.assertContains(r, 'value="complete"')

    def test_post_route_moves_the_holder_and_redirects(self):
        self.client.force_login(self.alice)
        r = self.client.post(
            self.url,
            {
                "workflow_dynamic_route_submit": "1",
                "action": "route",
                "target_user": self.bob.pk,
                "stage_label": "Finance review",
                "comment": "",
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.current_holder_id, self.bob.pk)

    def test_after_claim_only_the_holder_sees_the_route_form(self):
        self.submission.current_holder = self.bob
        self.submission.save(update_fields=["current_holder"])
        self.client.force_login(self.alice)
        r = self.client.get(self.url)
        self.assertNotContains(r, 'name="workflow_dynamic_route_submit"')
        self.assertContains(r, "currently with")

    def test_job_title_search_endpoint_matches_title(self):
        EmployeeProfile.objects.update_or_create(user=self.bob, defaults={"job_title": "Finance Manager"})
        self.client.force_login(self.alice)
        url = reverse("manage:user_search") + f"?q=Finance Manager&form={self._encoded_form_pk()}&scope=entity"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        ids = [row["id"] for row in data["results"]]
        self.assertIn(self.bob.pk, ids)
        matched = next(row for row in data["results"] if row["id"] == self.bob.pk)
        self.assertIn("Finance Manager", matched["text"])

    def _encoded_form_pk(self):
        from magicforms.opaque_ids import encode

        return encode(self.form.pk)


class _FakeRequest:
    def __init__(self, user):
        self.user = user


class DynamicFormIntegrationRegressionTests(TestCase):
    """
    Fixes for places that used to assume every form is fixed-step: publish readiness, the
    submissions-tab quick action, and who may sign documents.
    """

    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-dyn-regress")
        self.form = _dynamic_form(self.entity, slug="dyn-regress")
        FormField.objects.create(form=self.form, name="note", label="Note", field_type=FieldType.TEXT, order=0)
        User = get_user_model()
        self.holder = User.objects.create_user(username="holder1", password="x")
        self.other = User.objects.create_user(username="other1", password="x")
        EntityMembership.objects.create(user=self.holder, entity=self.entity)
        EntityMembership.objects.create(user=self.other, entity=self.entity)

    def test_dynamic_form_with_a_field_and_no_steps_may_publish(self):
        self.form.is_published = True
        self.form.save(update_fields=["is_published"])
        self.assertFalse(_maybe_unpublish(self.form))
        self.assertTrue(self.form.is_published)

    def test_dynamic_form_still_unpublishes_with_no_fields_at_all(self):
        bare = _dynamic_form(self.entity, slug="dyn-regress-bare")
        bare.is_published = True
        bare.save(update_fields=["is_published"])
        self.assertTrue(_maybe_unpublish(bare))
        self.assertFalse(bare.is_published)

    def test_leftover_workflow_steps_do_not_make_a_dynamic_form_act_fixed_step(self):
        # Simulates a form that was fixed-step and got switched to dynamic without deleting its steps.
        WorkflowStep.objects.create(form=self.form, order=0, label="Old step", slug="old-step")
        sub = FormSubmission.objects.create(form=self.form, current_holder=self.holder)
        # The old inline decision engine must still refuse (routing_mode gate), regardless of
        # the leftover WorkflowStep row.
        from magicforms.workflow_decision import perform_workflow_decision

        ok, err, result = perform_workflow_decision(user=self.holder, submission=sub, decision="approve")
        self.assertFalse(ok)

    def test_only_the_holder_may_sign_a_dynamic_submission_document(self):
        sub = FormSubmission.objects.create(form=self.form, current_holder=self.holder)
        self.assertTrue(_staff_may_sign_document(_FakeRequest(self.holder), sub))
        self.assertFalse(_staff_may_sign_document(_FakeRequest(self.other), sub))

    def test_nobody_may_sign_an_unclaimed_dynamic_submission_via_the_step_based_helper(self):
        # Signing specifically requires being the (current) holder; an unclaimed submission has none yet.
        sub = FormSubmission.objects.create(form=self.form)
        self.assertFalse(_staff_may_sign_document(_FakeRequest(self.holder), sub))
