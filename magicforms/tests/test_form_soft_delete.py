"""Organization admins (forms-write) can delete forms (soft delete) and restore them."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from magicforms.models import Entity, EntityMembership, Form


class FormSoftDeleteTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.entity = Entity.objects.create(name="Org", slug="org")
        self.form = Form.objects.create(entity=self.entity, title="Leave", slug="leave", is_published=True)
        self.admin = User.objects.create_user(username="admin", password="x")
        EntityMembership.objects.create(user=self.admin, entity=self.entity, manage_forms_write=True)
        self.reader = User.objects.create_user(username="reader", password="x")
        EntityMembership.objects.create(user=self.reader, entity=self.entity, manage_forms_read=True)
        self.delete_url = reverse("manage:form_archive", kwargs={"pk": self.form.pk})
        self.restore_url = reverse("manage:form_restore", kwargs={"pk": self.form.pk})
        self.detail_url = reverse("manage:form_detail", kwargs={"pk": self.form.pk})

    def test_admin_sees_delete_button_and_can_soft_delete(self):
        self.client.force_login(self.admin)
        r = self.client.get(self.detail_url)
        self.assertContains(r, "Delete form")
        r = self.client.post(self.delete_url)  # no confirmation word
        self.assertEqual(r.status_code, 302)
        self.form.refresh_from_db()
        self.assertIsNone(self.form.deleted_at)
        r = self.client.post(self.delete_url, {"confirm": "Confirm"})
        self.assertEqual(r.status_code, 302)
        from magicforms.opaque_ids import encode

        self.assertIn("undo=%s" % encode(self.form.pk), r["Location"])
        self.assertNotIn("undo=%d" % self.form.pk, r["Location"])
        self.form.refresh_from_db()
        self.assertIsNotNone(self.form.deleted_at)
        self.assertFalse(self.form.is_published)
        r = self.client.get(r["Location"])
        self.assertContains(r, "Undo")

    def test_admin_can_open_deleted_form_and_restore_it(self):
        self.client.force_login(self.admin)
        self.client.post(self.delete_url, {"confirm": "confirm"})
        r = self.client.get(self.detail_url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Restore form")
        r = self.client.post(self.restore_url, {"next": reverse("manage:dashboard")})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("manage:dashboard"))
        self.form.refresh_from_db()
        self.assertIsNone(self.form.deleted_at)

    def test_deleted_forms_listing_for_admin(self):
        self.client.force_login(self.admin)
        self.client.post(self.delete_url, {"confirm": "confirm"})
        r = self.client.get(reverse("manage:dashboard"))
        self.assertContains(r, "Deleted forms")
        self.assertNotContains(r, 'href="' + self.detail_url + '"')  # gone from the active list
        r = self.client.get(reverse("manage:dashboard") + "?archive=1")
        self.assertContains(r, "Leave")
        self.assertContains(r, "Restore")  # trash rows restore in place

    def test_read_only_member_cannot_delete_or_restore(self):
        self.client.force_login(self.reader)
        r = self.client.get(self.detail_url)
        self.assertNotContains(r, "Delete form")
        r = self.client.post(self.delete_url, {"confirm": "confirm"})
        self.assertEqual(r.status_code, 302)  # sent to login / denied
        self.form.refresh_from_db()
        self.assertIsNone(self.form.deleted_at)
