"""Responses grid column sorting."""

from django.test import TestCase

from magicforms.models import Entity, Form, FormField, FormSubmission
from magicforms.responses_grid_columns import (
    GRID_SORT_DEFAULT_KEY,
    apply_responses_grid_sort,
    parse_grid_sort,
)


class ResponsesGridSortTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-sort")
        self.form = Form.objects.create(
            entity=self.entity,
            title="Sort form",
            slug="sort-form",
            is_published=True,
        )
        self.field_a = FormField.objects.create(
            form=self.form,
            name="score",
            label="Score",
            field_type="text",
            order=0,
        )
        self.field_b = FormField.objects.create(
            form=self.form,
            name="note",
            label="Note",
            field_type="text",
            order=1,
        )
        self.sub_low = FormSubmission.objects.create(form=self.form, reference_token="REF-00000001")
        self.sub_high = FormSubmission.objects.create(form=self.form, reference_token="REF-00000099")
        self.sub_low.values.create(field=self.field_a, value="1")
        self.sub_high.values.create(field=self.field_a, value="9")

    def test_parse_grid_sort_defaults_to_submitted_desc(self):
        keys = ["meta:reference", "meta:submitted", f"field:{self.field_a.pk}"]
        key, desc = parse_grid_sort(None, None, keys)
        self.assertEqual(key, GRID_SORT_DEFAULT_KEY)
        self.assertTrue(desc)

    def test_parse_grid_sort_respects_visible_columns(self):
        keys = ["meta:reference"]
        key, desc = parse_grid_sort("meta:reference", "asc", keys)
        self.assertEqual(key, "meta:reference")
        self.assertFalse(desc)

    def test_sort_by_field_value_ascending(self):
        fields = list(self.form.get_ordered_fields())
        qs = apply_responses_grid_sort(
            self.form.submissions.all(),
            sort_key=f"field:{self.field_a.pk}",
            descending=False,
            fields=fields,
        )
        refs = list(qs.values_list("reference_token", flat=True))
        self.assertEqual(refs[0], "REF-00000001")
        self.assertEqual(refs[-1], "REF-00000099")
