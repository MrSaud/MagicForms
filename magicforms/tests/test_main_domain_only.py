"""Main-domain mode: organization subdomains are off; old subdomain links move to swapforms.com/e/<slug>/."""

from django.test import TestCase, override_settings

from magicforms.models import Entity, FieldType, Form, FormField, WorkflowStep


@override_settings(
    ALLOWED_HOSTS=["swapforms.com", "default.swapforms.com", "testserver"],
    MAGIFORM_BASE_DOMAIN="swapforms.com",
    MAGIFORM_DEFAULT_ENTITY_SLUG="default",
    MAGIFORM_SUBDOMAIN_PORTAL_ENABLED=False,
    SECURE_SSL_REDIRECT=False,
)
class MainDomainOnlyTests(TestCase):
    def setUp(self):
        self.entity, _ = Entity.objects.get_or_create(slug="default", defaults={"name": "Default organization"})
        Entity.objects.filter(pk=self.entity.pk).update(is_active=True)
        self.form = Form.objects.create(entity=self.entity, title="Main", slug="main", is_for_public=True)
        FormField.objects.create(form=self.form, name="name", label="Name", field_type=FieldType.TEXT, order=0)
        WorkflowStep.objects.create(form=self.form, order=0, label="One", slug="one")
        Form.objects.filter(pk=self.form.pk).update(is_published=True)  # publishable once it has a field and a step

    def test_root_is_the_landing_page_and_portal_lives_under_e(self):
        r = self.client.get("/", HTTP_HOST="swapforms.com")
        self.assertContains(r, "mf-landing-hero")
        r = self.client.get("/e/default/", HTTP_HOST="swapforms.com")
        self.assertEqual(r.status_code, 200, r.content[:300])
        r = self.client.get("/e/default/f/main/", HTTP_HOST="swapforms.com")
        self.assertEqual(r.status_code, 200)

    def test_legacy_short_link_on_apex_redirects_to_e_path(self):
        r = self.client.get("/f/main/", HTTP_HOST="swapforms.com")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].endswith("/e/default/f/main/"), r["Location"])

    def test_old_subdomain_links_move_to_the_main_domain(self):
        r = self.client.get("/f/main/", HTTP_HOST="default.swapforms.com")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "http://swapforms.com/e/default/f/main/")
        r = self.client.get("/", HTTP_HOST="default.swapforms.com")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "http://swapforms.com/e/default/")
        r = self.client.get("/manage/login/", HTTP_HOST="default.swapforms.com")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "http://swapforms.com/manage/login/")
