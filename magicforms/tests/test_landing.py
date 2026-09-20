"""The landing page and icon fallbacks are reachable on the apex portal host as well as plain hosts."""

from django.test import TestCase, override_settings

from magicforms.models import Entity


@override_settings(
    ALLOWED_HOSTS=["swapforms.com", "testserver"],
    MAGIFORM_BASE_DOMAIN="swapforms.com",
    MAGIFORM_DEFAULT_ENTITY_SLUG="default",
    MAGIFORM_SUBDOMAIN_PORTAL_ENABLED=True,  # documents the portal-enabled behaviour of the apex root
)
class LandingPageTests(TestCase):
    def setUp(self):
        ent, _ = Entity.objects.get_or_create(slug="default", defaults={"name": "Default organization"})
        Entity.objects.filter(pk=ent.pk).update(is_active=True)

    def test_apex_root_is_the_default_portal_but_welcome_is_the_landing_page(self):
        root = self.client.get("/", HTTP_HOST="swapforms.com")
        self.assertEqual(root.status_code, 200)
        self.assertNotContains(root, "mf-landing-hero")
        page = self.client.get("/welcome/", HTTP_HOST="swapforms.com")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "mf-landing-hero")
        self.assertContains(page, "/welcome/")  # wordmark and footer link back to the landing page

    def test_icon_fallbacks_route_on_the_apex_host(self):
        r = self.client.get("/favicon.ico", HTTP_HOST="swapforms.com")
        self.assertEqual(r.status_code, 302)
        self.assertIn("favicon-32.png", r["Location"])

    def test_plain_host_root_is_the_landing_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "mf-landing-hero")
