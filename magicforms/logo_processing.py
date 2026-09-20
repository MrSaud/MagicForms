"""Raster image uploads (portal logos, user signatures): knock near-white pixels to transparent (PNG output)."""

from __future__ import annotations

import io
import uuid
# JPEG/scan noise: treat very light neutrals as background
_DEFAULT_THRESHOLD = 248
_MAX_LONG_SIDE = 1400


def knockout_near_white_to_png(raw: bytes, original_filename: str) -> bytes | None:
    """
    Return PNG bytes with near-white pixels made transparent, or ``None`` to keep original.

    Skips SVG, GIF, and failures. Output is always PNG when processing runs.
    """
    name = (original_filename or "").lower()
    if name.endswith((".svg", ".gif")):
        return None
    if not name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return None
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        im = Image.open(io.BytesIO(raw))
        if getattr(im, "is_animated", False):
            return None
        im = im.convert("RGBA")
    except Exception:
        return None

    w, h = im.size
    if max(w, h) > _MAX_LONG_SIDE:
        im.thumbnail((_MAX_LONG_SIDE, _MAX_LONG_SIDE), Image.Resampling.LANCZOS)

    th = _DEFAULT_THRESHOLD
    pixels = list(im.getdata())
    out_pixels: list[tuple[int, int, int, int]] = []
    for (r, g, b, a) in pixels:
        if a and r >= th and g >= th and b >= th:
            out_pixels.append((r, g, b, 0))
        else:
            out_pixels.append((r, g, b, a))

    out = Image.new("RGBA", im.size)
    out.putdata(out_pixels)

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def maybe_replace_image_field_with_knockout_png(filefield: FieldFile) -> None:
    """
    If Pillow can strip a light background from a raster upload, replace the field file with PNG.

    No-op for SVG, GIF, unsupported types, Pillow missing, or processing errors.
    """
    if not filefield or not filefield.name:
        return
    name = filefield.name.lower()
    if name.endswith((".svg", ".gif")):
        return

    try:
        filefield.open("rb")
        try:
            raw = filefield.read()
        finally:
            filefield.close()
    except Exception:
        return

    processed = knockout_near_white_to_png(raw, filefield.name)
    if not processed:
        return

    from django.core.files.base import ContentFile

    stem = uuid.uuid4().hex[:12]
    filefield.save(f"{stem}.png", ContentFile(processed), save=False)
