"""Activity log middleware and staff-only studio access."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from magicforms.models import ActivityLog, Entity, EntityMembership


class ActivityLogTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.entity = Entity.objects.create(name="Acme", slug="acme")
        self.staff = User.objects.create_user("staff_log", password="x", is_staff=True)
        self.member = User.objects.create_user("member_log", password="x", is_staff=False)
        EntityMembership.objects.create(user=self.staff, entity=self.entity)
        EntityMembership.objects.create(user=self.member, entity=self.entity)
        self.client = Client()

    def test_middleware_logs_manage_request(self):
        self.client.force_login(self.staff)
        self.client.get(reverse("manage:dashboard"))
        self.assertTrue(
            ActivityLog.objects.filter(
                username="staff_log",
                channel=ActivityLog.Channel.WEB_MANAGE,
                http_method="GET",
            ).exists()
        )

    def test_middleware_logs_public_home(self):
        self.client.get(reverse("magicforms:home"))
        self.assertTrue(
            ActivityLog.objects.filter(
                path="/",
                channel=ActivityLog.Channel.WEB_OTHER,
            ).exists()
        )

    def test_staff_can_view_activity_log(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("manage:activity_log_list"))
        self.assertEqual(r.status_code, 200)

    def test_non_staff_cannot_view_activity_log(self):
        self.client.force_login(self.member)
        r = self.client.get(reverse("manage:activity_log_list"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("manage:dashboard"))
