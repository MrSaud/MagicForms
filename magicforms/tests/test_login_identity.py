from django.test import SimpleTestCase

from magicforms.login_identity import parse_login_identity


class ParseLoginIdentityTests(SimpleTestCase):
    def test_splits_longest_slug_prefix(self):
        parsed = parse_login_identity(
            "mosa-kuwait-jdoe",
            ["mosa", "mosa-kuwait"],
        )
        self.assertEqual(parsed.entity_slug, "mosa-kuwait")
        self.assertEqual(parsed.username, "jdoe")

    def test_no_slug_when_unknown_prefix(self):
        parsed = parse_login_identity("jdoe", ["mosa-kuwait"])
        self.assertIsNone(parsed.entity_slug)
        self.assertEqual(parsed.username, "jdoe")

    def test_empty_input(self):
        parsed = parse_login_identity("  ", ["default"])
        self.assertIsNone(parsed.entity_slug)
        self.assertEqual(parsed.username, "")
