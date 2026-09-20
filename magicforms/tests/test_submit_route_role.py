"""
Role-based auto-routing for dynamic-routing forms (Form.submit_route_role,
FormSubmitRoutePick): a fresh submission auto-claims itself on behalf of whoever holds the
configured role, favoring whoever has been picked most often for this form; a human's manual
pick on an unclaimed submission adds one to that person's count.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from magicforms.models import (
    EmployeeProfile,
    Entity,
    EntityMembership,
    FieldType,
    Form,
    FormField,
    FormSubmission,
    FormSubmitRoutePick,
    SubmissionEvent,
)
from magicforms.staff_forms import StaffMetaForm
from magicforms.workflow_decision import apply_submit_route_role, perform_dynamic_route_decision


class SubmitRouteRoleDefaultsTests(TestCase):
    def test_new_forms_default_to_no_role_and_no_picks(self):
        entity = Entity.objects.create(name="Org", slug="org-submit-route-default")
        form = Form.objects.create(entity=entity, title="F", slug="f-submit-route-default")
        self.assertEqual(form.submit_route_role, "")
        self.assertFalse(FormSubmitRoutePick.objects.filter(form=form).exists())


class StaffMetaFormSubmitRouteRoleTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-submit-route-form")
        self.form = Form.objects.create(
            entity=self.entity,
            title="F",
            slug="f-submit-route-form",
            routing_mode=Form.RoutingMode.DYNAMIC,
        )
        self.staff = get_user_model().objects.create_user(
            username="staff-submit-route", password="x", is_staff=True
        )
        EntityMembership.objects.create(user=self.staff, entity=self.entity, view_responses_write=True)

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
            "submit_route_role": "",
            "hide_from_form_lists": "",
        }
        data.update(overrides)
        return data

    def test_role_is_optional(self):
        form = StaffMetaForm(
            self._form_data(), instance=self.form, staff_user=self.staff, request=None
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_setting_a_role_saves_it(self):
        form = StaffMetaForm(
            self._form_data(submit_route_role="Finance Manager"),
            instance=self.form,
            staff_user=self.staff,
            request=None,
        )
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        obj.refresh_from_db()
        self.assertEqual(obj.submit_route_role, "Finance Manager")

    def test_settings_page_shows_the_role_field(self):
        self.client.force_login(self.staff)
        url = reverse("manage:form_edit", kwargs={"pk": self.form.pk})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="submit_route_role"')


def _dynamic_form(entity, slug="dyn-submit-route", role=""):
    return Form.objects.create(
        entity=entity,
        title="Dynamic",
        slug=slug,
        routing_mode=Form.RoutingMode.DYNAMIC,
        submit_route_role=role,
    )


def _pick(form, user, times):
    FormSubmitRoutePick.objects.create(form=form, user=user, times_picked=times)


class ApplySubmitRouteRoleTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-apply-route-role")
        User = get_user_model()
        self.finn = User.objects.create_user(username="finn-route", password="x")
        self.gwen = User.objects.create_user(username="gwen-route", password="x")
        for u in (self.finn, self.gwen):
            EntityMembership.objects.create(user=u, entity=self.entity)

    def _submission(self, form):
        return FormSubmission.objects.create(form=form)

    def test_fixed_step_form_is_untouched(self):
        form = Form.objects.create(
            entity=self.entity, title="F", slug="f-apply-fixed", submit_route_role="Finance"
        )
        sub = self._submission(form)
        apply_submit_route_role(sub)
        sub.refresh_from_db()
        self.assertIsNone(sub.current_holder_id)

    def test_blank_role_is_a_no_op(self):
        form = _dynamic_form(self.entity, role="")
        sub = self._submission(form)
        apply_submit_route_role(sub)
        sub.refresh_from_db()
        self.assertIsNone(sub.current_holder_id)

    def test_no_one_holds_the_role_stays_unclaimed(self):
        form = _dynamic_form(self.entity, role="Finance Manager")
        sub = self._submission(form)
        apply_submit_route_role(sub)
        sub.refresh_from_db()
        self.assertIsNone(sub.current_holder_id)

    def test_exactly_one_holder_auto_routes_even_with_no_picks_yet(self):
        EmployeeProfile.objects.update_or_create(user=self.finn, defaults={"job_title": "Finance Manager"})
        form = _dynamic_form(self.entity, role="Finance Manager")
        sub = self._submission(form)
        apply_submit_route_role(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.current_holder_id, self.finn.pk)
        self.assertTrue(
            SubmissionEvent.objects.filter(submission=sub, kind=SubmissionEvent.Kind.ROUTED).exists()
        )

    def test_multiple_holders_no_picks_stays_unclaimed(self):
        EmployeeProfile.objects.update_or_create(user=self.finn, defaults={"job_title": "Finance Manager"})
        EmployeeProfile.objects.update_or_create(user=self.gwen, defaults={"job_title": "Finance Manager"})
        form = _dynamic_form(self.entity, role="Finance Manager")
        sub = self._submission(form)
        apply_submit_route_role(sub)
        sub.refresh_from_db()
        self.assertIsNone(sub.current_holder_id)

    def test_multiple_holders_tied_pick_counts_stays_unclaimed(self):
        EmployeeProfile.objects.update_or_create(user=self.finn, defaults={"job_title": "Finance Manager"})
        EmployeeProfile.objects.update_or_create(user=self.gwen, defaults={"job_title": "Finance Manager"})
        form = _dynamic_form(self.entity, role="Finance Manager")
        _pick(form, self.finn, 2)
        _pick(form, self.gwen, 2)
        sub = self._submission(form)
        apply_submit_route_role(sub)
        sub.refresh_from_db()
        self.assertIsNone(sub.current_holder_id)

    def test_multiple_holders_the_most_picked_one_wins(self):
        EmployeeProfile.objects.update_or_create(user=self.finn, defaults={"job_title": "Finance Manager"})
        EmployeeProfile.objects.update_or_create(user=self.gwen, defaults={"job_title": "Finance Manager"})
        form = _dynamic_form(self.entity, role="Finance Manager")
        _pick(form, self.finn, 1)
        _pick(form, self.gwen, 3)
        sub = self._submission(form)
        apply_submit_route_role(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.current_holder_id, self.gwen.pk)

    def test_pick_for_someone_who_no_longer_holds_the_role_is_ignored(self):
        EmployeeProfile.objects.update_or_create(user=self.finn, defaults={"job_title": "Finance Manager"})
        form = _dynamic_form(self.entity, role="Finance Manager")
        _pick(form, self.gwen, 5)  # gwen was picked before but doesn't hold the role at all
        sub = self._submission(form)
        apply_submit_route_role(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.current_holder_id, self.finn.pk)

    def test_picks_on_a_different_form_do_not_count(self):
        EmployeeProfile.objects.update_or_create(user=self.finn, defaults={"job_title": "Finance Manager"})
        EmployeeProfile.objects.update_or_create(user=self.gwen, defaults={"job_title": "Finance Manager"})
        form = _dynamic_form(self.entity, slug="dyn-a", role="Finance Manager")
        other_form = _dynamic_form(self.entity, slug="dyn-b", role="Finance Manager")
        _pick(other_form, self.gwen, 9)  # heavily picked, but on a different form
        sub = self._submission(form)
        apply_submit_route_role(sub)
        sub.refresh_from_db()
        # No picks recorded on *this* form and two candidates: stays open.
        self.assertIsNone(sub.current_holder_id)


class SubmitRouteRolePickCountingTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-learn-route-role")
        User = get_user_model()
        self.finn = User.objects.create_user(username="finn-learn", password="x")
        self.gwen = User.objects.create_user(username="gwen-learn", password="x")
        self.holder = User.objects.create_user(username="holder-learn", password="x")
        for u in (self.finn, self.gwen, self.holder):
            EntityMembership.objects.create(user=u, entity=self.entity)
        EmployeeProfile.objects.update_or_create(user=self.finn, defaults={"job_title": "Finance Manager"})
        EmployeeProfile.objects.update_or_create(user=self.gwen, defaults={"job_title": "Marketing Lead"})

    def _route(self, form, sub, target_pk, actor=None):
        ok, err, result = perform_dynamic_route_decision(
            user=actor or self.holder, submission=sub, action="route", target_user_id=target_pk
        )
        self.assertTrue(ok, err)

    def test_manual_route_on_unclaimed_submission_to_a_role_holder_is_counted(self):
        form = _dynamic_form(self.entity, role="Finance Manager")
        sub = FormSubmission.objects.create(form=form)
        self._route(form, sub, self.finn.pk)
        pick = FormSubmitRoutePick.objects.get(form=form, user=self.finn)
        self.assertEqual(pick.times_picked, 1)

    def test_three_separate_submissions_routed_to_the_same_holder_accumulate(self):
        form = _dynamic_form(self.entity, role="Finance Manager")
        for _ in range(3):
            sub = FormSubmission.objects.create(form=form)
            self._route(form, sub, self.finn.pk)
        pick = FormSubmitRoutePick.objects.get(form=form, user=self.finn)
        self.assertEqual(pick.times_picked, 3)

    def test_manual_route_to_someone_outside_the_role_is_not_counted(self):
        form = _dynamic_form(self.entity, role="Finance Manager")
        sub = FormSubmission.objects.create(form=form)
        self._route(form, sub, self.gwen.pk)
        self.assertFalse(FormSubmitRoutePick.objects.filter(form=form, user=self.gwen).exists())

    def test_second_hop_routing_does_not_add_a_pick(self):
        form = _dynamic_form(self.entity, role="Finance Manager")
        sub = FormSubmission.objects.create(form=form, current_holder=self.finn)
        # finn already holds it (second hop); routing on to someone else must not count.
        self._route(form, sub, self.holder.pk, actor=self.finn)
        self.assertFalse(FormSubmitRoutePick.objects.filter(form=form, user=self.holder).exists())


class SubmitRouteRoleEndToEndTests(TestCase):
    def test_public_submission_auto_claims_via_role(self):
        entity = Entity.objects.create(name="Org", slug="org-e2e-route-role")
        User = get_user_model()
        finn = User.objects.create_user(username="finn-e2e", password="x")
        EntityMembership.objects.create(user=finn, entity=entity)
        EmployeeProfile.objects.update_or_create(user=finn, defaults={"job_title": "Finance Manager"})

        form = Form.objects.create(
            entity=entity,
            title="F",
            slug="f-e2e-route-role",
            is_published=True,
            is_for_public=True,
            routing_mode=Form.RoutingMode.DYNAMIC,
            submit_route_role="Finance Manager",
        )
        field = FormField.objects.create(
            form=form, name="name", label="Name", field_type=FieldType.TEXT, order=0
        )
        url = reverse(
            "magicforms:form_public", kwargs={"entity_slug": entity.slug, "slug": form.slug}
        )
        r = self.client.post(url, {f"f_{field.pk}": "Ada"})
        self.assertEqual(r.status_code, 302, getattr(r, "content", None))
        sub = FormSubmission.objects.get(form=form)
        self.assertEqual(sub.current_holder_id, finn.pk)
