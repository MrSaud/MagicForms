"""ReportLab PDF text: Arabic shaping and bundled Noto Sans Arabic fonts."""

from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

_ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)

_FONTS_DIR = Path(__file__).resolve().parent / "fonts"
_FONT_REGULAR_FILE = "NotoSansArabic-Regular.ttf"
_FONT_BOLD_FILE = "NotoSansArabic-Bold.ttf"

FONT_REGULAR_NAME = "NotoSansArabic"
FONT_BOLD_NAME = "NotoSansArabic-Bold"
FONT_FALLBACK_REGULAR = "Helvetica"
FONT_FALLBACK_BOLD = "Helvetica-Bold"


def _needs_arabic_shaping(text: str) -> bool:
    return bool(_ARABIC_RE.search(text))


def prepare_pdf_text(text: str) -> str:
    """Reshape and apply bidi for Arabic script so ReportLab renders connected glyphs in order."""
    if text is None:
        return ""
    s = str(text)
    if not s or not _needs_arabic_shaping(s):
        return s
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        return s
    return get_display(arabic_reshaper.reshape(s))


def pdf_paragraph_markup(text: str) -> str:
    """Escaped HTML for ReportLab ``Paragraph`` (preserves line breaks)."""
    return html.escape(prepare_pdf_text(text)).replace("\r\n", "\n").replace("\n", "<br/>")


def _font_file_candidates(filename: str) -> list[Path]:
    paths = [_FONTS_DIR / filename]
    for base in (
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/google-noto",
        "/usr/share/fonts/opentype/noto",
        "/System/Library/Fonts/Supplemental",
        "/Library/Fonts",
    ):
        paths.append(Path(base) / filename)
    return paths


def _resolve_font_path(filename: str) -> Path | None:
    for p in _font_file_candidates(filename):
        if p.is_file():
            return p
    return None


@lru_cache(maxsize=1)
def pdf_font_names() -> tuple[str, str]:
    """
    Register bundled/system Noto Sans Arabic with ReportLab when available.

    Returns ``(regular_font_name, bold_font_name)`` for ``ParagraphStyle`` / ``TableStyle``.
    """
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return FONT_FALLBACK_REGULAR, FONT_FALLBACK_BOLD

    regular_path = _resolve_font_path(_FONT_REGULAR_FILE)
    bold_path = _resolve_font_path(_FONT_BOLD_FILE)

    if regular_path:
        if FONT_REGULAR_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(FONT_REGULAR_NAME, str(regular_path)))
        reg = FONT_REGULAR_NAME
    else:
        reg = FONT_FALLBACK_REGULAR

    if bold_path:
        if FONT_BOLD_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(FONT_BOLD_NAME, str(bold_path)))
        bold = FONT_BOLD_NAME
    elif regular_path:
        bold = reg
    else:
        bold = FONT_FALLBACK_BOLD

    return reg, bold


def pdf_cell_paragraph(text: str, *, font_size: float = 7, leading: float | None = None):
    """ReportLab ``Paragraph`` for a table cell using the PDF Unicode font."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    reg, _ = pdf_font_names()
    lead = leading if leading is not None else max(font_size + 2, font_size * 1.25)
    style = ParagraphStyle(
        name=f"PdfCell_{font_size}",
        fontName=reg,
        fontSize=font_size,
        leading=lead,
        wordWrap="CJK",
    )
    return Paragraph(pdf_paragraph_markup(text), style)


def pdf_title_paragraph(text: str, *, font_size: float = 14):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    reg, _ = pdf_font_names()
    style = ParagraphStyle(
        name="PdfTitle",
        fontName=reg,
        fontSize=font_size,
        leading=font_size + 4,
        spaceAfter=6,
        wordWrap="CJK",
    )
    return Paragraph(pdf_paragraph_markup(text), style)


def pdf_meta_paragraph(text: str, *, font_size: float = 9):
    """Secondary lines under a PDF title (reference, status, etc.)."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    reg, _ = pdf_font_names()
    style = ParagraphStyle(
        name=f"PdfMeta_{font_size}",
        fontName=reg,
        fontSize=font_size,
        leading=font_size + 3,
        spaceAfter=2,
        wordWrap="CJK",
    )
    return Paragraph(pdf_paragraph_markup(text), style)


def pdf_header_cell_paragraph(text: str, *, font_size: float = 8):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    _, bold = pdf_font_names()
    style = ParagraphStyle(
        name=f"PdfHeader_{font_size}",
        fontName=bold,
        fontSize=font_size,
        leading=font_size + 2,
        textColor=colors.white,
        wordWrap="CJK",
    )
    return Paragraph(pdf_paragraph_markup(text), style)
