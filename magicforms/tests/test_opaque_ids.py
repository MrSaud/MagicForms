"""Studio links never expose plain database ids."""

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from magicforms.opaque_ids import TOKEN_LENGTH, decode, encode, parse_id


class OpaqueIdTests(SimpleTestCase):
    def test_round_trip_and_shape(self):
        for pk in (0, 1, 2, 7, 12345, 2**31, 2**32 - 1):
            tok = encode(pk)
            self.assertEqual(len(tok), TOKEN_LENGTH)
            self.assertFalse(tok.isdigit())
            self.assertEqual(decode(tok), pk)
        self.assertNotEqual(encode(1), encode(2))
        self.assertIsNone(decode("2"))
        self.assertIsNone(decode("zzzzzzz!"))
        self.assertEqual(parse_id("15"), 15)
        self.assertEqual(parse_id(encode(15)), 15)
        self.assertIsNone(parse_id(""))

    def test_tokens_depend_on_the_secret(self):
        a = encode(42)
        with override_settings(SECRET_KEY="another-secret-for-the-test"):
            b = encode(42)
        self.assertNotEqual(a, b)


class OpaqueUrlTests(TestCase):
    def test_studio_urls_use_tokens_not_numbers(self):
        url = reverse("manage:form_detail", kwargs={"pk": 2})
        self.assertNotIn("/2/", url)
        self.assertIn("/" + encode(2) + "/", url)
        sub = reverse("manage:submission_manage_detail", kwargs={"pk": 2, "submission_id": 23})
        self.assertNotIn("/23/", sub)
        self.assertEqual(self.client.get("/manage/forms/2/").status_code, 404)
