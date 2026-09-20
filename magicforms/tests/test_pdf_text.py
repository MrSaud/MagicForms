from django.test import SimpleTestCase

from magicforms.pdf_text import prepare_pdf_text, pdf_font_names


class PdfTextTests(SimpleTestCase):
    def test_prepare_pdf_text_passes_latin_unchanged(self):
        self.assertEqual(prepare_pdf_text("Hello 123"), "Hello 123")

    def test_prepare_pdf_text_shapes_arabic(self):
        raw = "مرحبا"
        shaped = prepare_pdf_text(raw)
        self.assertIsInstance(shaped, str)
        self.assertTrue(shaped)

    def test_pdf_font_names_registers_noto(self):
        reg, bold = pdf_font_names()
        self.assertIn(reg, ("NotoSansArabic", "Helvetica"))
        self.assertTrue(bold)
