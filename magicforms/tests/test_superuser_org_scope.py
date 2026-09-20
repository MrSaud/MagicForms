"""Super admins must choose an organization before the studio opens."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from magicforms.entity_access import MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY
from magicforms.models import Entity, EntityMembership, Form


class SuperuserOrganizationScopeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.org_a = Entity.objects.create(name="Alpha Org", slug="alpha")
        self.org_b = Entity.objects.create(name="Beta Org", slug="beta")
        Form.objects.create(entity=self.org_a, title="A1", slug="a1")
        self.superuser = User.objects.create_superuser(username="root", password="x", email="root@example.com")
        self.staff = User.objects.create_user(username="staff", password="x", is_staff=True)
        EntityMembership.objects.create(user=self.staff, entity=self.org_a)
        self.chooser = reverse("manage:choose_organization")

    def test_superuser_without_scope_is_sent_to_chooser(self):
        self.client.force_login(self.superuser)
        r = self.client.get(reverse("manage:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith(self.chooser))
        self.assertIn("next=", r["Location"])

    def test_chooser_lists_and_searches_organizations(self):
        self.client.force_login(self.superuser)
        r = self.client.get(self.chooser)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Alpha Org")
        self.assertContains(r, "Beta Org")
        r = self.client.get(self.chooser, {"q": "beta"})
        # The top-bar scope selector lists every organization, so inspect the chooser grid only.
        html = r.content.decode()
        grid = html.split('class="mf-org-choice__grid"', 1)[1].split("</ul>", 1)[0]
        self.assertIn("Beta Org", grid)
        self.assertNotIn("Alpha Org", grid)

    def test_choosing_sets_scope_and_unlocks_studio(self):
        self.client.force_login(self.superuser)
        r = self.client.post(
            reverse("manage:superuser_entity_scope"),
            {"entity_id": self.org_a.pk, "next": reverse("manage:inbox")},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("manage:inbox"))
        self.assertEqual(self.client.session[MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY], self.org_a.pk)
        r = self.client.get(reverse("manage:dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Alpha Org")

    def test_login_and_logout_stay_reachable(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("manage:login")).status_code, 302)  # already signed in
        r = self.client.post(reverse("manage:logout"))
        self.assertIn(r.status_code, (200, 302))

    def test_non_superusers_are_not_gated(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("manage:dashboard"))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(self.chooser)
        self.assertIn(r.status_code, (302, 403))
