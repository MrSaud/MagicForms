"""AI assistance stays hidden (buttons, assistant panel, endpoints) until MAGIFORM_AI_FEATURES_ENABLED is on."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from magicforms.manage_views import MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY
from magicforms.models import Entity


class AiHiddenTests(TestCase):
    def setUp(self):
        self.entity, _ = Entity.objects.get_or_create(slug="org", defaults={"name": "Org"})
        boss = get_user_model().objects.create_superuser(username="boss", password="x", email="b@x.invalid")
        self.client.force_login(boss)
        session = self.client.session
        session[MANAGE_SUPERUSER_ENTITY_SCOPE_SESSION_KEY] = self.entity.pk
        session.save()

    @override_settings(MAGIFORM_AI_FEATURES_ENABLED=False)
    def test_hidden_by_default(self):
        r = self.client.get(reverse("manage:dashboard"))
        self.assertNotContains(r, "Create with AI")
        r = self.client.get(reverse("manage:inbox"))
        self.assertNotContains(r, "Inbox assistant")
        self.assertNotContains(r, "inbox_ai_chat.js")
        self.assertEqual(self.client.get(reverse("manage:form_generate_from_text")).status_code, 404)
        self.assertEqual(self.client.post(reverse("manage:inbox_ai_chat"), {"q": "x"}).status_code, 404)

    @override_settings(MAGIFORM_AI_FEATURES_ENABLED=True)
    def test_visible_when_enabled(self):
        r = self.client.get(reverse("manage:dashboard"))
        self.assertContains(r, "Create with AI")
        self.assertEqual(self.client.get(reverse("manage:form_generate_from_text")).status_code, 200)
