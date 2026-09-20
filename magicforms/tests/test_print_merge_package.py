"""DOCX package rewrite: duplicate zip entries are removed so LibreOffice can load the file."""

import io
import zipfile

from django.test import SimpleTestCase

from magicforms.print_merge import _rewrite_docx_package

_SETTINGS = b'<?xml version="1.0" encoding="UTF-8"?><w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'


def _docx_with_duplicate_core() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", b"<Types/>")
        z.writestr("word/document.xml", b"<w:document/>")
        z.writestr("word/settings.xml", _SETTINGS)
        z.writestr("docProps/core.xml", b"<cp:coreProperties>old</cp:coreProperties>")
        z.writestr("docProps/core.xml", b"<cp:coreProperties>new</cp:coreProperties>")
    return buf.getvalue()


class RewriteDocxPackageTests(SimpleTestCase):
    def test_duplicate_entries_are_collapsed_keeping_last(self):
        out = _rewrite_docx_package(_docx_with_duplicate_core(), read_only_marks=False)
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            names = z.namelist()
            self.assertEqual(len(names), len(set(names)))
            self.assertEqual(names.count("docProps/core.xml"), 1)
            self.assertIn(b"new", z.read("docProps/core.xml"))
            self.assertEqual(z.read("word/settings.xml"), _SETTINGS)

    def test_read_only_marks_patch_settings(self):
        out = _rewrite_docx_package(_docx_with_duplicate_core(), read_only_marks=True)
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            settings_xml = z.read("word/settings.xml")
        self.assertIn(b"documentProtection", settings_xml)
        self.assertIn(b"readOnlyRecommended", settings_xml)
