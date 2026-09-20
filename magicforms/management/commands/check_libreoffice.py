"""Verify LibreOffice is usable for DOCX/ODT → PDF (in-page document preview)."""

import io
import zipfile

from django.core.management.base import BaseCommand

from magicforms.print_merge import (
    PrintMergeError,
    docx_to_pdf_available,
    libreoffice_bytes_to_pdf,
    libreoffice_diagnostic_report,
)


def _minimal_docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>test</w:t></w:r></w:p></w:body></w:document>",
        )
        zf.writestr(
            "word/_rels/document.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            "</Relationships>",
        )
    return buf.getvalue()


class Command(BaseCommand):
    help = "Check that headless LibreOffice can convert DOCX to PDF (submission Read document preview)."

    def handle(self, *args, **options):
        self.stdout.write(libreoffice_diagnostic_report())
        self.stdout.write("")
        if not docx_to_pdf_available():
            self.stderr.write(
                self.style.ERROR(
                    "No working soffice binary. LibreOffice is probably not installed.\n"
                    "  Amazon Linux 2023: install RPMs from libreoffice.org (see DEPLOY.md), then\n"
                    "    find /opt -name soffice\n"
                    "  RHEL-style: sudo dnf install -y libreoffice libreoffice-headless\n"
                    "  Set MAGIFORM_SOFFICE=/opt/libreofficeNN.N/program/soffice (NOT soffice.bin).\n"
                    "  Then: sudo systemctl restart magicforms"
                )
            )
            raise SystemExit(1)
        try:
            pdf = libreoffice_bytes_to_pdf(_minimal_docx_bytes(), "probe", "docx")
            self.stdout.write(self.style.SUCCESS(f"Test conversion OK ({len(pdf)} byte PDF)."))
        except PrintMergeError as exc:
            self.stderr.write(self.style.ERROR(f"Test conversion failed: {exc}"))
            raise SystemExit(1) from exc
