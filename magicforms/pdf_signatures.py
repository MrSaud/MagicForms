"""
Stamp hand-drawn signatures onto generated PDFs.

Placements come from the public document page: the respondent right-clicks a point on the
rendered page (pdf.js, origin top-left), draws a signature, and the point plus the drawing are
stored as a ``SubmissionSignaturePlacement``. Here the displayed coordinates are mapped back to
PDF user space (origin bottom-left, honouring ``/Rotate``) and the image is merged as an overlay.
"""

from __future__ import annotations

import io
from typing import Any, Iterable, Protocol

SIGNATURE_MIN_WIDTH_FRACTION = 0.05
SIGNATURE_MAX_WIDTH_FRACTION = 0.6
SIGNATURE_DEFAULT_WIDTH_FRACTION = 0.22


class PlacementLike(Protocol):
    page_index: int
    x: float
    y: float
    width: float

    def image_bytes(self) -> bytes: ...


def _page_rotation(page: Any) -> int:
    try:
        rot = int(page.get("/Rotate", 0) or 0)
    except (TypeError, ValueError):
        rot = 0
    return rot % 360


def displayed_to_user_space(
    dx: float, dy: float, page_w: float, page_h: float, rotation: int
) -> tuple[float, float]:
    """
    Map a point given as fractions of the *displayed* page (origin top-left, after ``/Rotate``)
    to unrotated PDF user-space coordinates (origin bottom-left).
    """
    dx = min(max(dx, 0.0), 1.0)
    dy = min(max(dy, 0.0), 1.0)
    if rotation == 90:
        return dy * page_w, dx * page_h
    if rotation == 180:
        return (1.0 - dx) * page_w, dy * page_h
    if rotation == 270:
        return (1.0 - dy) * page_w, (1.0 - dx) * page_h
    return dx * page_w, (1.0 - dy) * page_h


def _prepare_signature_png(raw: bytes, rotation: int) -> tuple[bytes, float]:
    """Return (PNG bytes rotated to appear upright on the displayed page, aspect = h / w in display)."""
    from PIL import Image as PILImage

    im = PILImage.open(io.BytesIO(raw))
    im = im.convert("RGBA")
    im.thumbnail((1400, 1400), PILImage.Resampling.LANCZOS)
    display_aspect = im.height / float(im.width or 1)
    if rotation:
        # PIL rotates counter-clockwise; the page is displayed rotated clockwise by ``rotation``.
        im = im.rotate(rotation, expand=True)
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue(), display_aspect


def stamp_signature_placements(pdf_bytes: bytes, placements: Iterable[PlacementLike]) -> bytes:
    """Merge every placement onto its page; on any failure return ``pdf_bytes`` unchanged."""
    by_page: dict[int, list[PlacementLike]] = {}
    for p in placements:
        by_page.setdefault(int(p.page_index), []).append(p)
    if not by_page:
        return pdf_bytes

    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as rl_canvas
    except ImportError:
        return pdf_bytes

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        for index, page in enumerate(reader.pages):
            todo = by_page.get(index) or []
            if todo:
                mb = page.mediabox
                pw, ph = float(mb.width), float(mb.height)
                rotation = _page_rotation(page)
                disp_w, disp_h = (ph, pw) if rotation in (90, 270) else (pw, ph)
                overlay_buf = io.BytesIO()
                overlay_canvas = rl_canvas.Canvas(overlay_buf, pagesize=(pw, ph))
                drew_any = False
                for p in todo:
                    try:
                        png, aspect = _prepare_signature_png(p.image_bytes(), rotation)
                    except Exception:
                        continue

                    frac = min(
                        max(float(p.width or SIGNATURE_DEFAULT_WIDTH_FRACTION), SIGNATURE_MIN_WIDTH_FRACTION),
                        SIGNATURE_MAX_WIDTH_FRACTION,
                    )
                    disp_sig_w = frac * disp_w
                    disp_sig_h = disp_sig_w * aspect
                    # Box size in user space (swapped when the page is rotated sideways).
                    box_w, box_h = (
                        (disp_sig_h, disp_sig_w) if rotation in (90, 270) else (disp_sig_w, disp_sig_h)
                    )
                    cx, cy = displayed_to_user_space(float(p.x), float(p.y), pw, ph, rotation)
                    x0 = cx - box_w / 2.0
                    y0 = cy - box_h / 2.0
                    # Keep the signature inside the page.
                    x0 = min(max(x0, 0.0), max(pw - box_w, 0.0))
                    y0 = min(max(y0, 0.0), max(ph - box_h, 0.0))
                    # mask="auto" keeps the PNG alpha channel, so only the ink is stamped.
                    overlay_canvas.drawImage(
                        ImageReader(io.BytesIO(png)), x0, y0, width=box_w, height=box_h, mask="auto"
                    )
                    drew_any = True
                if drew_any:
                    overlay_canvas.showPage()
                    overlay_canvas.save()
                    overlay = PdfReader(io.BytesIO(overlay_buf.getvalue())).pages[0]
                    page.merge_page(overlay)
            writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return pdf_bytes


def decode_signature_data_url(data_url: str, *, max_bytes: int = 600_000) -> bytes:
    """
    Validate a ``data:image/png;base64,...`` payload from the signature pad and return normalized PNG
    bytes (RGBA, trimmed of empty margins). Raises ``ValueError`` on anything unexpected.
    """
    import base64

    from PIL import Image as PILImage

    if not isinstance(data_url, str) or not data_url.startswith("data:image/png;base64,"):
        raise ValueError("Signature must be a PNG image.")
    b64 = data_url.split(",", 1)[1]
    if len(b64) > max_bytes * 4 // 3 + 4:
        raise ValueError("Signature image is too large.")
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception as exc:
        raise ValueError("Signature image is not valid.") from exc
    try:
        im = PILImage.open(io.BytesIO(raw))
        im.verify()
        im = PILImage.open(io.BytesIO(raw)).convert("RGBA")
    except Exception as exc:
        raise ValueError("Signature image is not valid.") from exc
    if im.width > 2000 or im.height > 2000:
        raise ValueError("Signature image is too large.")
    bbox = im.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("Draw your signature before placing it.")
    pad = 6
    bbox = (
        max(bbox[0] - pad, 0),
        max(bbox[1] - pad, 0),
        min(bbox[2] + pad, im.width),
        min(bbox[3] + pad, im.height),
    )
    im = im.crop(bbox)
    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()


def normalize_signature_file_bytes(raw: bytes, *, max_bytes: int = 2_000_000) -> bytes:
    """
    Turn a stored signature image (PNG/JPG/WebP/GIF upload) into the RGBA PNG the stamper expects.
    Opaque scans get a transparent background (near-white pixels become clear). Raises ``ValueError``.
    """
    from PIL import Image as PILImage

    if not raw or len(raw) > max_bytes:
        raise ValueError("Saved signature image is too large.")
    try:
        im = PILImage.open(io.BytesIO(raw))
        im.verify()
        im = PILImage.open(io.BytesIO(raw))
        had_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA")
    except Exception as exc:
        raise ValueError("Saved signature must be a PNG, JPG, WebP or GIF image.") from exc
    if im.width > 3000 or im.height > 3000:
        im.thumbnail((3000, 3000))
    if not had_alpha:
        px = im.load()
        for y in range(im.height):
            for x in range(im.width):
                r, g, b, _a = px[x, y]
                if min(r, g, b) > 235:
                    px[x, y] = (r, g, b, 0)
    bbox = im.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("Saved signature image is blank.")
    im = im.crop(bbox)
    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()
