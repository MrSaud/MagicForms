from django.test import TestCase

from magicforms.dynamic_forms import build_public_form, serialize_value
from magicforms.field_validation import submission_value_already_exists
from magicforms.models import Entity, FieldType, Form, FormField, FormSubmission, SubmissionValue


class FieldUniqueValidationTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Acme", slug="acme")
        self.form = Form.objects.create(entity=self.entity, title="App", slug="app")
        self.field = FormField.objects.create(
            form=self.form,
            name="national_id",
            label="National ID",
            field_type=FieldType.TEXT,
            validation_unique_value=True,
        )

    def test_duplicate_value_detected(self):
        sub = FormSubmission.objects.create(form=self.form)
        SubmissionValue.objects.create(
            submission=sub,
            field=self.field,
            value=serialize_value(self.field, "123456"),
        )
        self.assertTrue(
            submission_value_already_exists(self.field, "123456"),
        )

    def test_unique_value_passes_public_form(self):
        sub = FormSubmission.objects.create(form=self.form)
        SubmissionValue.objects.create(
            submission=sub,
            field=self.field,
            value="111",
        )
        FormClass = build_public_form(self.form)
        form = FormClass({"f_{}".format(self.field.pk): "222"})
        self.assertTrue(form.is_valid())

    def test_duplicate_rejected_on_public_form(self):
        sub = FormSubmission.objects.create(form=self.form)
        SubmissionValue.objects.create(
            submission=sub,
            field=self.field,
            value="111",
        )
        FormClass = build_public_form(self.form)
        form = FormClass({"f_{}".format(self.field.pk): "111"})
        self.assertFalse(form.is_valid())
        self.assertIn("f_{}".format(self.field.pk), form.errors)
