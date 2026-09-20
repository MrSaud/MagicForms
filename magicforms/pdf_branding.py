"""Stamp organization (entity) portal logos onto generated PDFs."""

from __future__ import annotations

import io
import os
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Entity

LOGO_MARGIN_PT = 28.0
LOGO_MAX_HEIGHT_PT = 36.0
LOGO_MAX_WIDTH_PT = 140.0


def stamp_entity_logo_on_pdf(pdf_bytes: bytes, entity: Entity | None) -> bytes:
    """
    Merge each page with a small logo in the top-left corner (when ``entity.page_logo`` is set).

    SVG logos are skipped (raster-only pipeline). On failure, returns ``pdf_bytes`` unchanged.
    """
    if not entity or not getattr(entity, "page_logo", None) or not entity.page_logo:
        return pdf_bytes
    name = (entity.page_logo.name or "").lower()
    if name.endswith(".svg"):
        return pdf_bytes
    try:
        from PIL import Image as PILImage
        from pypdf import PdfReader, PdfWriter
        from reportlab.graphics import renderPDF
        from reportlab.graphics.shapes import Drawing, Image as RLImage
    except ImportError:
        return pdf_bytes

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if not reader.pages:
            return pdf_bytes
    except Exception:
        return pdf_bytes

    logo_png = io.BytesIO()
    try:
        with entity.page_logo.open("rb") as f:
            raw = f.read()
        im = PILImage.open(io.BytesIO(raw))
        if im.mode == "P":
            im = im.convert("RGBA")
        elif im.mode in ("L", "LA"):
            im = im.convert("RGBA")
        elif im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        im.thumbnail((480, 480), PILImage.Resampling.LANCZOS)
        if im.mode == "RGBA":
            im.save(logo_png, format="PNG")
        else:
            im.convert("RGB").save(logo_png, format="PNG")
    except Exception:
        return pdf_bytes

    logo_path = ""
    try:
        fd, logo_path = tempfile.mkstemp(suffix=".mf-entity-logo.png")
        os.write(fd, logo_png.getvalue())
        os.close(fd)

        writer = PdfWriter()
        overlay_cache: dict[tuple[float, float], bytes] = {}

        for page in reader.pages:
            mb = page.mediabox
            pw = float(mb.width)
            ph = float(mb.height)
            key = (round(pw, 2), round(ph, 2))
            if key not in overlay_cache:
                lw, lh = _logo_draw_size_points(logo_path, LOGO_MAX_WIDTH_PT, LOGO_MAX_HEIGHT_PT)
                d = Drawing(pw, ph)
                d.add(
                    RLImage(
                        LOGO_MARGIN_PT,
                        ph - LOGO_MARGIN_PT - lh,
                        width=lw,
                        height=lh,
                        path=logo_path,
                    )
                )
                overlay_cache[key] = renderPDF.drawToString(d)
            overlay_page = PdfReader(io.BytesIO(overlay_cache[key])).pages[0]
            page.merge_page(overlay_page)
            writer.add_page(page)

        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return pdf_bytes
    finally:
        if logo_path:
            try:
                os.unlink(logo_path)
            except OSError:
                pass


def _logo_draw_size_points(logo_path: str, max_w: float, max_h: float) -> tuple[float, float]:
    from PIL import Image as PILImage

    im = PILImage.open(logo_path)
    pw, ph = im.size
    if pw < 1 or ph < 1:
        return max_w * 0.5, max_h * 0.5
    scale = min(max_w / pw, max_h / ph)
    return max(1.0, pw * scale), max(1.0, ph * scale)
