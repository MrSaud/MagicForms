from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from magicforms.models import (
    Entity,
    EntityMembership,
    Form,
    FormSubmission,
    SubmissionEvent,
    WorkflowDelegation,
    WorkflowStep,
)
from magicforms.print_merge import (
    _applicant_signature_fallback_plain,
    _approver_on_behalf_for_event,
    _approver_signature_fallback_plain,
    _approver_signature_fallback_text,
    _delegation_on_behalf_lines,
)

User = get_user_model()


class PrintMergeSignatureFallbackTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-merge")
        self.form = Form.objects.create(entity=self.entity, title="T", slug="t")
        self.applicant = User.objects.create_user(username="applicant", password="x")
        self.applicant.first_name = "Sara"
        self.applicant.last_name = "Ali"
        self.applicant.save()
        EntityMembership.objects.create(user=self.applicant, entity=self.entity)
        self.delegator = User.objects.create_user(username="mgr", password="x", is_staff=True)
        self.delegate = User.objects.create_user(username="delegate", password="x", is_staff=True)
        EntityMembership.objects.create(user=self.delegator, entity=self.entity)
        EntityMembership.objects.create(user=self.delegate, entity=self.entity)
        self.step = WorkflowStep.objects.create(form=self.form, label="Review", slug="review", order=0)
        self.step.assigned_users.add(self.delegator)
        self.submission = FormSubmission.objects.create(
            form=self.form,
            submitted_by=self.applicant,
            submitted_at=timezone.now(),
        )

    def test_applicant_fallback_submit_date_only(self):
        text = _applicant_signature_fallback_plain(self.submission)
        self.assertNotIn("Sara", text)
        self.assertNotIn("Ali", text)
        self.assertNotIn("Submitted:", text)
        self.assertRegex(text, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_delegation_on_behalf_bilingual(self):
        WorkflowDelegation.objects.create(
            entity=self.entity,
            delegator=self.delegator,
            delegate=self.delegate,
            valid_from=date.today(),
            is_active=True,
        )
        when = timezone.now()
        lines = _delegation_on_behalf_lines(self.delegate, self.step, self.entity.pk, when)
        self.assertIn("On behalf of", lines)
        self.assertIn("mgr", lines)
        self.assertIn("نيابة عن", lines)

    def test_approver_fallback_date_only_not_delegation(self):
        WorkflowDelegation.objects.create(
            entity=self.entity,
            delegator=self.delegator,
            delegate=self.delegate,
            is_active=True,
        )
        ev = SubmissionEvent.objects.create(
            submission=self.submission,
            kind=SubmissionEvent.Kind.STEP_APPROVED,
            step=self.step,
            created_by=self.delegate,
        )
        text = _approver_signature_fallback_text(ev, self.submission)
        self.assertNotIn("delegate", text)
        self.assertNotIn("Approved:", text)
        self.assertNotIn("On behalf of", text)
        self.assertRegex(text, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertEqual(text, _approver_signature_fallback_plain(ev))

    def test_approver_on_behalf_empty_when_step_assignee_approves(self):
        ev = SubmissionEvent.objects.create(
            submission=self.submission,
            kind=SubmissionEvent.Kind.STEP_APPROVED,
            step=self.step,
            created_by=self.delegator,
        )
        self.assertEqual(_approver_on_behalf_for_event(ev, self.submission), "")

    def test_approver_on_behalf_when_delegate_approves(self):
        WorkflowDelegation.objects.create(
            entity=self.entity,
            delegator=self.delegator,
            delegate=self.delegate,
            is_active=True,
        )
        ev = SubmissionEvent.objects.create(
            submission=self.submission,
            kind=SubmissionEvent.Kind.STEP_APPROVED,
            step=self.step,
            created_by=self.delegate,
        )
        text = _approver_on_behalf_for_event(ev, self.submission)
        self.assertIn("On behalf of", text)
        self.assertIn("mgr", text)
