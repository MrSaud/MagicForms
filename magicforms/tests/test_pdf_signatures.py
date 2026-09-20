"""Signature placements: coordinate mapping, PDF stamping, and payload validation (no DB needed)."""

import base64
import io
from types import SimpleNamespace

from django.test import SimpleTestCase

from magicforms.pdf_signatures import (
    decode_signature_data_url,
    displayed_to_user_space,
    stamp_signature_placements,
)


def _blank_pdf(pages=2, width=595, height=842, rotate=0) -> bytes:
    from pypdf import PdfWriter

    w = PdfWriter()
    for _ in range(pages):
        page = w.add_blank_page(width=width, height=height)
        if rotate:
            page.rotate(rotate)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def _signature_png(w=300, h=120) -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.line([(20, 90), (120, 20), (200, 100), (280, 30)], fill=(16, 24, 40, 255), width=4)
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


class DisplayedToUserSpaceTests(SimpleTestCase):
    def test_unrotated_top_left_and_bottom_right(self):
        self.assertEqual(displayed_to_user_space(0, 0, 100, 200, 0), (0, 200))
        self.assertEqual(displayed_to_user_space(1, 1, 100, 200, 0), (100, 0))
        self.assertEqual(displayed_to_user_space(0.5, 0.5, 100, 200, 0), (50, 100))

    def test_rotated_90_maps_display_to_user_space(self):
        # Display of a /Rotate 90 page is 200 wide × 100 high; its top-left is the page's bottom-left.
        self.assertEqual(displayed_to_user_space(0, 0, 100, 200, 90), (0, 0))
        self.assertEqual(displayed_to_user_space(1, 0, 100, 200, 90), (0, 200))
        self.assertEqual(displayed_to_user_space(0, 1, 100, 200, 90), (100, 0))

    def test_rotated_180_and_270(self):
        self.assertEqual(displayed_to_user_space(0, 0, 100, 200, 180), (100, 0))
        self.assertEqual(displayed_to_user_space(0, 0, 100, 200, 270), (100, 200))

    def test_out_of_range_is_clamped(self):
        self.assertEqual(displayed_to_user_space(-3, 7, 100, 200, 0), (0, 0))


class StampSignaturePlacementsTests(SimpleTestCase):
    def _placement(self, **kw):
        png = _signature_png()
        base = dict(page_index=0, x=0.5, y=0.8, width=0.25, image_bytes=lambda: png)
        base.update(kw)
        return SimpleNamespace(**base)

    def test_stamps_image_only_on_target_page(self):
        from pypdf import PdfReader

        pdf = _blank_pdf(pages=2)
        out = stamp_signature_placements(pdf, [self._placement(page_index=1)])
        self.assertNotEqual(out, pdf)
        reader = PdfReader(io.BytesIO(out))
        self.assertEqual(len(reader.pages), 2)
        self.assertFalse(reader.pages[0].images)
        self.assertEqual(len(reader.pages[1].images), 1)

    def test_no_placements_returns_input_unchanged(self):
        pdf = _blank_pdf()
        self.assertIs(stamp_signature_placements(pdf, []), pdf)

    def test_rotated_page_still_receives_image(self):
        from pypdf import PdfReader

        pdf = _blank_pdf(pages=1, rotate=90)
        out = stamp_signature_placements(pdf, [self._placement()])
        self.assertEqual(len(PdfReader(io.BytesIO(out)).pages[0].images), 1)

    def test_broken_signature_image_is_skipped_not_fatal(self):
        pdf = _blank_pdf(pages=1)
        out = stamp_signature_placements(pdf, [self._placement(image_bytes=lambda: b"not a png")])
        self.assertTrue(out.startswith(b"%PDF"))


class DecodeSignatureDataUrlTests(SimpleTestCase):
    def _data_url(self, png: bytes) -> str:
        return "data:image/png;base64," + base64.b64encode(png).decode()

    def test_valid_signature_is_cropped_to_ink(self):
        from PIL import Image

        out = decode_signature_data_url(self._data_url(_signature_png(600, 300)))
        im = Image.open(io.BytesIO(out))
        self.assertEqual(im.mode, "RGBA")
        self.assertLess(im.width, 600)
        self.assertLess(im.height, 300)

    def test_blank_canvas_is_rejected(self):
        from PIL import Image

        im = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        with self.assertRaises(ValueError):
            decode_signature_data_url(self._data_url(buf.getvalue()))

    def test_non_png_and_garbage_are_rejected(self):
        with self.assertRaises(ValueError):
            decode_signature_data_url("data:image/jpeg;base64,AAAA")
        with self.assertRaises(ValueError):
            decode_signature_data_url("data:image/png;base64,!!!notbase64!!!")
        with self.assertRaises(ValueError):
            decode_signature_data_url(self._data_url(b"garbage"))
