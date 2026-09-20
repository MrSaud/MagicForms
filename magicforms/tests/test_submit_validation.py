from unittest.mock import patch

from django.test import TestCase

from django.contrib.auth import get_user_model

from magicforms.models import Entity, FieldType, Form, FormField, FormSubmitValidationConfig, FormSubmission, SubmissionValue
from magicforms.responses_grid_applicant import applicant_meta_values
from magicforms.responses_grid_columns import META_COLUMN_KEYS, build_projected_grid_rows

User = get_user_model()
from magicforms.submit_validation.messages import (
    applicant_validation_message,
    extract_api_message,
    render_applicant_message,
)
from magicforms.submit_validation.payload import build_pre_submit_validation_payload
from magicforms.responses_grid_applicant import attach_studio_list_applicant, guest_identity_field_display
from magicforms.submit_validation.runner import check_pre_submit_validation


class ResponsesGridApplicantTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-grid")
        self.form = Form.objects.create(entity=self.entity, title="T", slug="t")
        self.user = User.objects.create_user(username="applicant1", email="a@example.com")
        self.user.first_name = "Ada"
        self.user.last_name = "Lovelace"
        self.user.save()

    def test_applicant_column_in_grid(self):
        sub = FormSubmission.objects.create(
            form=self.form,
            submitter_email="fallback@example.com",
            submitted_by=self.user,
        )
        meta = applicant_meta_values(sub)
        self.assertEqual(meta["applicant_name"], "Ada Lovelace")
        self.assertIn("Ada Lovelace", meta["applicant"])
        # The email typed at submit time wins over the account email (see _best_applicant_email).
        self.assertEqual(meta["email"], "fallback@example.com")
        headers, rows = build_projected_grid_rows([sub], [], META_COLUMN_KEYS)
        self.assertIn("Applicant", headers)
        idx = META_COLUMN_KEYS.index("meta:applicant")
        self.assertIn("Ada Lovelace", rows[0][idx])

    def test_guest_applicant_field_replaces_requested_by_prefix(self):
        field = FormField.objects.create(
            form=self.form,
            name="applicant",
            label="Applicant name",
            field_type=FieldType.TEXT,
            order=0,
        )
        sub = FormSubmission.objects.create(form=self.form, submitter_email="guest@example.com")
        SubmissionValue.objects.create(submission=sub, field=field, value="Sara Ali")
        attach_studio_list_applicant(sub)
        self.assertTrue(sub.inbox_applicant_prefix_is_field_label)
        self.assertEqual(sub.inbox_applicant_prefix, "Applicant name")
        self.assertEqual(sub.inbox_applicant_guest_value, "Sara Ali")

    def test_inbox_applicant_empty_shows_anonymous(self):
        sub = FormSubmission.objects.create(form=self.form)
        attach_studio_list_applicant(sub)
        self.assertEqual(sub.inbox_applicant_prefix, "Requested by:")
        self.assertEqual(sub.inbox_applicant_guest_value, "Anonymous")

    def test_guest_identity_field_priority(self):
        FormField.objects.create(
            form=self.form, name="email", label="Email", field_type=FieldType.EMAIL, order=0
        )
        name_f = FormField.objects.create(
            form=self.form, name="name", label="Full name", field_type=FieldType.TEXT, order=1
        )
        sub = FormSubmission.objects.create(form=self.form)
        SubmissionValue.objects.create(submission=sub, field=name_f, value="Priority Name")
        got = guest_identity_field_display(sub)
        self.assertEqual(got, ("Full name", "Priority Name"))


class SubmitValidationPayloadTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org")
        self.form = Form.objects.create(entity=self.entity, title="T", slug="t")

    def test_payload_includes_form_and_entity(self):
        body = build_pre_submit_validation_payload(self.form, {}, [], request=None)
        self.assertEqual(body["phase"], "pre_submit")
        self.assertEqual(body["form"]["slug"], "t")
        self.assertEqual(body["entity"]["slug"], "org")


class SubmitValidationMessageTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-msg")
        self.form = Form.objects.create(entity=self.entity, title="M", slug="m")
        self.config = FormSubmitValidationConfig.objects.create(
            form=self.form,
            message_rejected="Rejected {{status}}: {{api_message}}",
            message_unreachable="Network down.",
            message_error="Server error.",
        )

    def test_render_placeholders(self):
        out = render_applicant_message(
            "Code {{status}} — {{api_message}}",
            {"status": "422", "api_message": "Invalid ID"},
        )
        self.assertEqual(out, "Code 422 — Invalid ID")

    def test_extract_api_message_from_json(self):
        self.assertEqual(
            extract_api_message('{"message": "Not eligible"}'),
            "Not eligible",
        )

    def test_custom_rejected_message(self):
        msg = applicant_validation_message(
            self.config,
            "rejected",
            status=403,
            api_message="No access",
        )
        self.assertEqual(msg, "Rejected 403: No access")

    def test_blank_uses_default(self):
        self.config.message_unreachable = ""
        self.config.save(update_fields=["message_unreachable"])
        msg = applicant_validation_message(self.config, "unreachable")
        self.assertIn("validation service", msg.lower())


class SubmitValidationRunnerTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org2")
        self.form = Form.objects.create(entity=self.entity, title="F", slug="f")

    def test_no_config_proceeds(self):
        result = check_pre_submit_validation(self.form, {}, [], request=None)
        self.assertTrue(result.proceed)

    def test_inactive_config_proceeds(self):
        FormSubmitValidationConfig.objects.create(
            form=self.form,
            is_active=False,
            endpoint_url="https://example.com/validate",
        )
        result = check_pre_submit_validation(self.form, {}, [], request=None)
        self.assertTrue(result.proceed)

    @patch("magicforms.submit_validation.runner.send_json_integration_post")
    def test_non_200_blocks_when_configured(self, mock_post):
        mock_post.return_value = (400, '{"message": "bad"}', {}, {})
        FormSubmitValidationConfig.objects.create(
            form=self.form,
            is_active=True,
            endpoint_url="https://example.com/validate",
            auth_type="none",
            failure_action=FormSubmitValidationConfig.FailureAction.BLOCK,
        )
        result = check_pre_submit_validation(self.form, {}, [], request=None)
        self.assertFalse(result.proceed)
        self.assertFalse(result.can_force_submit)

    @patch("magicforms.submit_validation.runner.send_json_integration_post")
    def test_non_200_uses_custom_applicant_message(self, mock_post):
        mock_post.return_value = (422, '{"detail": "Wrong dept"}', {}, {})
        FormSubmitValidationConfig.objects.create(
            form=self.form,
            is_active=True,
            endpoint_url="https://example.com/validate",
            auth_type="none",
            message_rejected="Sorry: {{api_message}} ({{status}})",
        )
        result = check_pre_submit_validation(self.form, {}, [], request=None)
        self.assertEqual(result.message, "Sorry: Wrong dept (422)")

    @patch("magicforms.submit_validation.runner.send_json_integration_post")
    def test_non_200_allows_force_when_configured(self, mock_post):
        mock_post.return_value = (422, "nope", {}, {})
        FormSubmitValidationConfig.objects.create(
            form=self.form,
            is_active=True,
            endpoint_url="https://example.com/validate",
            auth_type="none",
            failure_action=FormSubmitValidationConfig.FailureAction.ALLOW_CONTINUE,
        )
        blocked = check_pre_submit_validation(self.form, {}, [], request=None)
        self.assertFalse(blocked.proceed)
        self.assertTrue(blocked.can_force_submit)
        forced = check_pre_submit_validation(
            self.form, {}, [], request=None, force_submit=True
        )
        self.assertTrue(forced.proceed)

    @patch("magicforms.submit_validation.runner.send_json_integration_post")
    def test_200_proceeds(self, mock_post):
        mock_post.return_value = (200, "ok", {}, {})
        FormSubmitValidationConfig.objects.create(
            form=self.form,
            is_active=True,
            endpoint_url="https://example.com/validate",
            auth_type="none",
        )
        result = check_pre_submit_validation(self.form, {}, [], request=None)
        self.assertTrue(result.proceed)
