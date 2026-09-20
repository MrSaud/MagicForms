"""Form setting: default layout direction (RTL / LTR / follow language)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from magicforms.models import Entity, EntityMembership, Form


class FormLayoutDirectionTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org")
        self.form = Form.objects.create(entity=self.entity, title="F", slug="f")
        User = get_user_model()
        self.staff = User.objects.create_user(username="staff", password="x", is_staff=True)
        EntityMembership.objects.create(user=self.staff, entity=self.entity)

    def test_default_follows_language(self):
        self.assertEqual(self.form.layout_direction, Form.LayoutDirection.AUTO)
        with translation.override("en"):
            self.assertEqual(self.form.public_dir(), "ltr")
        with translation.override("ar"):
            self.assertEqual(self.form.public_dir(), "rtl")

    def test_pinned_direction_ignores_language(self):
        self.form.layout_direction = Form.LayoutDirection.LTR
        with translation.override("ar"):
            self.assertEqual(self.form.public_dir(), "ltr")
        self.form.layout_direction = Form.LayoutDirection.RTL
        with translation.override("en"):
            self.assertEqual(self.form.public_dir(), "rtl")

    def test_settings_page_shows_and_saves_option(self):
        self.client.force_login(self.staff)
        url = reverse("manage:form_edit", kwargs={"pk": self.form.pk})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="layout_direction"')
        self.assertContains(r, 'value="rtl"')

        r = self.client.post(
            url,
            {
                "entity": self.entity.pk,
                "title": "F",
                "description": "",
                "layout_direction": "rtl",
                "submission_deadline": "",
                "intro_capacity": "",
                "category": "",
            },
        )
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        self.form.refresh_from_db()
        self.assertEqual(self.form.layout_direction, "rtl")

    def test_public_form_html_uses_pinned_direction(self):
        from django.template.loader import render_to_string

        self.form.layout_direction = Form.LayoutDirection.RTL
        with translation.override("en"):
            html = render_to_string(
                "magicforms/form_public_closed.html",
                {"form_def": self.form, "LANGUAGE_CODE": "en", "LANGUAGE_BIDI": False},
            )
        self.assertIn('dir="rtl"', html)
