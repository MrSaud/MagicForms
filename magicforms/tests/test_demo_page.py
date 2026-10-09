"""The public product tour at /demo/: reachable without signing in on every host, bilingual, linked from the landing page."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import translation

from magicforms.models import Entity

TEMPLATE = Path(__file__).resolve().parents[1] / "templates/magicforms/demo.html"
TRANS_TAG = re.compile(
    r"""\{%\s*trans\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')(\s+context\s+[^%]*)?\s*%\}"""
)


class DemoPageTests(TestCase):
    def test_anyone_can_browse_it_without_signing_in(self):
        r = self.client.get("/demo/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "What is SwapForms?")
        for anchor in ('id="tour"', 'id="features"', 'id="uses"', 'id="values"', 'id="faq"'):
            self.assertContains(r, anchor)
        self.assertContains(r, "data-mf-tabs")

    def test_all_four_tour_stages_are_in_the_page_for_visitors_without_scripts(self):
        r = self.client.get("/demo/")
        for panel in ("mf-tour-build", "mf-tour-publish", "mf-tour-route", "mf-tour-deliver"):
            self.assertContains(r, f'id="{panel}"')

    def test_landing_page_and_footer_link_to_the_tour(self):
        r = self.client.get("/welcome/")
        self.assertContains(r, 'href="/demo/"')
        r = self.client.get("/demo/")
        self.assertContains(r, 'href="/welcome/"')

    def test_arabic_visitors_get_a_right_to_left_page_with_correct_pdf_wording(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ar"
        r = self.client.get("/demo/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'dir="rtl"')
        self.assertContains(r, "ما هو سواب فورمز؟")
        self.assertContains(r, "تنزيل PDF")
        self.assertNotContains(r, "قوات الدفاع الشعبي")


_HOSTS = dict(
    ALLOWED_HOSTS=["swapforms.com", "default.swapforms.com", "testserver"],
    MAGIFORM_BASE_DOMAIN="swapforms.com",
    MAGIFORM_DEFAULT_ENTITY_SLUG="default",
    SECURE_SSL_REDIRECT=False,
)


class _DefaultEntityMixin:
    def setUp(self):
        ent, _ = Entity.objects.get_or_create(slug="default", defaults={"name": "Default organization"})
        Entity.objects.filter(pk=ent.pk).update(is_active=True)


@override_settings(MAGIFORM_SUBDOMAIN_PORTAL_ENABLED=True, **_HOSTS)
class DemoPagePortalEnabledTests(_DefaultEntityMixin, TestCase):
    def test_reachable_on_the_apex_portal_host(self):
        r = self.client.get("/demo/", HTTP_HOST="swapforms.com")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "mf-demo-page")

    def test_landing_page_on_the_portal_host_links_to_the_tour(self):
        r = self.client.get("/welcome/", HTTP_HOST="swapforms.com")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'href="/demo/"')

    def test_organization_portal_home_still_renders(self):
        # Portal pages can run on a different urlconf; adding the tour route must not break them.
        r = self.client.get("/", HTTP_HOST="swapforms.com")
        self.assertEqual(r.status_code, 200, r.content[:300])


@override_settings(MAGIFORM_SUBDOMAIN_PORTAL_ENABLED=False, **_HOSTS)
class DemoPageMainDomainOnlyTests(_DefaultEntityMixin, TestCase):
    def test_reachable_on_the_main_domain(self):
        r = self.client.get("/demo/", HTTP_HOST="swapforms.com")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "mf-demo-page")

    def test_old_organization_subdomain_link_moves_to_the_main_domain(self):
        r = self.client.get("/demo/", HTTP_HOST="default.swapforms.com")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "http://swapforms.com/demo/")


class DemoPageTranslationTests(SimpleTestCase):
    def test_every_string_on_the_page_has_an_arabic_translation(self):
        source = TEMPLATE.read_text(encoding="utf-8")
        untranslated = []
        with translation.override("ar"):
            for m in TRANS_TAG.finditer(source):
                if m.group(3):
                    continue  # strings with a translation context are covered by their own catalogue entries
                msgid = m.group(1) if m.group(1) is not None else m.group(2)
                if translation.gettext(msgid) == msgid:
                    untranslated.append(msgid)
        self.assertEqual(untranslated, [], "Add Arabic entries for:\n" + "\n".join(untranslated))
