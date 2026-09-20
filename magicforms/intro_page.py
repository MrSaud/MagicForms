"""Helpers for the public form announcement (information) page."""

from __future__ import annotations

import re
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, urlparse

from django.utils.html import mark_safe
from django.utils.safestring import SafeString
from django.utils.translation import gettext as _

_ALLOWED_TAGS = frozenset(
    {
        "p",
        "br",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "a",
        "ul",
        "ol",
        "li",
        "h1",
        "h2",
        "h3",
        "div",
        "blockquote",
    }
)
_VOID_TAGS = frozenset({"br", "hr"})
_STRIP_WRAPPER_TAGS = frozenset({"span", "font", "mark"})


class _IntroHTMLCleaner(HTMLParser):
    """Allow a small HTML subset; drop unknown tags but keep their text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignore_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _VOID_TAGS:
            if tag == "br":
                self.parts.append("<br>")
            return
        if tag in _STRIP_WRAPPER_TAGS:
            return
        if tag not in _ALLOWED_TAGS:
            self._ignore_depth += 1
            return
        if tag == "a":
            attr_map = {k.lower(): v for k, v in attrs if v}
            href = (attr_map.get("href") or "").strip()
            if not href or href.startswith(("javascript:", "data:")):
                return
            rel = attr_map.get("rel") or "noopener noreferrer"
            target = attr_map.get("target") or "_blank"
            self.parts.append(
                f'<a href="{escape(href, quote=True)}" rel="{escape(rel)}" '
                f'target="{escape(target)}">'
            )
            return
        self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _VOID_TAGS or tag in _STRIP_WRAPPER_TAGS:
            return
        if tag not in _ALLOWED_TAGS:
            if self._ignore_depth > 0:
                self._ignore_depth -= 1
            return
        self.parts.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self._ignore_depth > 0:
            self.parts.append(escape(data))
        else:
            self.parts.append(escape(data))

    def handle_entityref(self, name):
        self.parts.append(f"&{name};")

    def handle_charref(self, name):
        self.parts.append(f"&#{name};")


def clean_intro_html(raw: str) -> str:
    """Return sanitized HTML for the announcement message body."""
    text = unescape((raw or "").strip())
    if not text:
        return ""
    if "<" not in text:
        return escape(text).replace("\n", "<br>\n")
    parser = _IntroHTMLCleaner()
    try:
        parser.feed(text)
        parser.close()
        cleaned = "".join(parser.parts).strip()
        if cleaned:
            return cleaned
    except Exception:
        pass
    return escape(text).replace("\n", "<br>\n")


def intro_description_markup(raw: str) -> SafeString:
    cleaned = clean_intro_html(raw)
    return mark_safe(cleaned) if cleaned else SafeString("")


_YOUTUBE_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})",
    re.I,
)
_VIMEO_RE = re.compile(r"vimeo\.com/(?:video/)?(\d+)", re.I)


def _youtube_video_id(url: str, parsed, host: str, path: str) -> str | None:
    m = _YOUTUBE_RE.search(url)
    if m:
        return m.group(1)
    if host == "youtu.be":
        part = path.strip("/").split("/")[0]
        return part if len(part) == 11 else None
    if host in ("youtube.com", "m.youtube.com"):
        if path.startswith(("/embed/", "/shorts/", "/live/")):
            part = path.strip("/").split("/")[1]
            return part if len(part) == 11 else None
        vid = (parse_qs(parsed.query).get("v") or [None])[0]
        return vid if vid and len(vid) == 11 else None
    return None


def parse_intro_video_embed(url: str) -> dict | None:
    """
    Return embed metadata for YouTube or Vimeo, or a plain external link.
    Keys: provider, embed_url, watch_url
    """
    u = (url or "").strip()
    if not u:
        return None
    if "://" not in u:
        u = f"https://{u}"
    parsed = urlparse(u)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = parsed.path or ""

    yt = _youtube_video_id(u, parsed, host, path)
    if yt:
        return {
            "provider": "youtube",
            "embed_url": f"https://www.youtube-nocookie.com/embed/{yt}",
            "watch_url": f"https://www.youtube.com/watch?v={yt}",
        }

    m = _VIMEO_RE.search(u)
    if m:
        vid = m.group(1)
        return {
            "provider": "vimeo",
            "embed_url": f"https://player.vimeo.com/video/{vid}",
            "watch_url": f"https://vimeo.com/{vid}",
        }

    if parsed.scheme in ("http", "https"):
        return {"provider": "link", "embed_url": "", "watch_url": u}
    return None


def intro_venue_type_label(venue_type: str) -> str:
    from .models import Form

    if not venue_type:
        return ""
    try:
        return Form.IntroVenueType(venue_type).label
    except ValueError:
        return venue_type


def _media_absolute_url(request, file_field) -> str:
    if not file_field or not getattr(file_field, "name", None):
        return ""
    url = file_field.url
    if url.startswith(("http://", "https://")):
        return url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def build_intro_share_fields(request, form_def) -> dict:
    """mailto / WhatsApp / QR image URL for the public announcement entry link."""
    from magicforms.subdomain import portal_absolute_uri

    share_url = form_def.build_public_form_absolute_url(request)
    title = (form_def.intro_title or "").strip() or form_def.title
    share_subject = _("Share: %(title)s") % {"title": title}
    share_body = _(
        "Please open this announcement page for \"%(title)s\":\n\n%(url)s"
    ) % {"title": title, "url": share_url}
    share_query = (
        {"share": str(form_def.public_share_key)} if form_def.public_share_key else None
    )
    qrcode_url = portal_absolute_uri(
        request,
        "magicforms:form_intro_qrcode",
        entity=form_def.entity,
        slug=form_def.slug,
        query=share_query,
    )
    return {
        "share_url": share_url,
        "share_mailto": (
            "mailto:?subject=" + quote(share_subject, safe="") + "&body=" + quote(share_body, safe="")
        ),
        "share_whatsapp": "https://wa.me/?text=" + quote(share_body, safe=""),
        "intro_qrcode_url": qrcode_url,
    }


def build_intro_page_context(request, form_def, *, studio_intro_preview: bool = False) -> dict:
    """Shared announcement page data for web templates and mobile API."""
    from django.utils.dateformat import format as date_format

    from .subdomain import portal_absolute_uri

    title = (form_def.intro_title or "").strip() or form_def.title
    deadline = form_def.submission_deadline
    seats_remaining = form_def.intro_seats_remaining()
    venue_type = (form_def.intro_venue_type or "").strip()

    slides = []
    for slide in form_def.get_ordered_intro_slides():
        if not slide.image or not slide.image.name:
            continue
        caption = (slide.caption or "").strip()
        slides.append(
            {
                "url": _media_absolute_url(request, slide.image),
                "caption": caption,
                "alt": caption or title,
            }
        )

    brochure_url = ""
    if form_def.intro_attachment and form_def.intro_attachment.name:
        brochure_url = portal_absolute_uri(
            request,
            "magicforms:form_intro_attachment",
            entity=form_def.entity,
            slug=form_def.slug,
            query=(
                {"share": str(form_def.public_share_key)}
                if form_def.public_share_key
                else None
            ),
        )

    return {
        "form_def": form_def,
        "intro_title": title,
        "intro_subtitle": (form_def.intro_subtitle or "").strip(),
        "intro_description_html": intro_description_markup(form_def.intro_description),
        "intro_details": form_def.intro_details_lines(),
        "intro_details_ordered": form_def.intro_details_use_ordered_list(),
        "intro_rules": form_def.intro_rules_lines(),
        "intro_rules_ordered": form_def.intro_rules_use_ordered_list(),
        "intro_event_start": form_def.intro_event_start,
        "intro_event_end": form_def.intro_event_end,
        "intro_slides": slides,
        "intro_venue_type": venue_type,
        "intro_venue_label": str(intro_venue_type_label(venue_type)) if venue_type else "",
        "intro_location": (form_def.intro_location or "").strip(),
        "intro_map_url": (form_def.intro_map_url or "").strip(),
        "intro_contact_name": (form_def.intro_contact_name or "").strip(),
        "intro_contact_email": (form_def.intro_contact_email or "").strip(),
        "intro_contact_phone": (form_def.intro_contact_phone or "").strip(),
        "intro_fee": (form_def.intro_fee or "").strip(),
        "intro_capacity": form_def.intro_capacity,
        "intro_show_capacity": form_def.intro_show_capacity_on_page(),
        "intro_seats_remaining": seats_remaining,
        "intro_video": parse_intro_video_embed(form_def.intro_video_url),
        "intro_apply_label": str(form_def.intro_apply_label()),
        "has_intro_attachment": bool(form_def.intro_attachment and form_def.intro_attachment.name),
        "intro_brochure_url": brochure_url,
        "registration_deadline": deadline,
        "registration_deadline_label": date_format(deadline, "M j, Y") if deadline else "",
        "apply_url": form_def.build_public_apply_url(request),
        "closed": form_def.submission_deadline_has_passed(),
        "studio_intro_preview": studio_intro_preview,
        **build_intro_share_fields(request, form_def),
    }


def serialize_form_intro_api(request, form_def) -> dict:
    """JSON-serializable announcement page for native mobile clients."""
    from django.utils import timezone
    from django.utils.dateformat import format as date_format

    ctx = build_intro_page_context(request, form_def)
    video = ctx.get("intro_video")

    def _dt_label(dt) -> str:
        if not dt:
            return ""
        return date_format(timezone.localtime(dt), "M j, Y, P")

    return {
        "form_id": form_def.pk,
        "enabled": bool(form_def.intro_page_enabled),
        "headline": ctx["intro_title"],
        "tagline": ctx["intro_subtitle"],
        "message_html": str(ctx["intro_description_html"] or ""),
        "highlights": ctx["intro_details"],
        "highlights_list_style": form_def.intro_details_list_style,
        "guidelines": ctx["intro_rules"],
        "guidelines_list_style": form_def.intro_rules_list_style,
        "gallery": [
            {"image_url": s["url"], "caption": s["caption"], "alt": s["alt"]}
            for s in ctx["intro_slides"]
        ],
        "schedule": {
            "starts_at": (
                form_def.intro_event_start.isoformat()
                if form_def.intro_event_start
                else ""
            ),
            "ends_at": (
                form_def.intro_event_end.isoformat() if form_def.intro_event_end else ""
            ),
            "starts_label": _dt_label(form_def.intro_event_start),
            "ends_label": _dt_label(form_def.intro_event_end),
        },
        "register_by": {
            "date": (
                ctx["registration_deadline"].isoformat()
                if ctx["registration_deadline"]
                else ""
            ),
            "label": ctx["registration_deadline_label"],
        },
        "where": {
            "format": ctx["intro_venue_type"],
            "format_label": ctx["intro_venue_label"],
            "location": ctx["intro_location"],
            "map_url": ctx["intro_map_url"],
        },
        "contact": {
            "name": ctx["intro_contact_name"],
            "email": ctx["intro_contact_email"],
            "phone": ctx["intro_contact_phone"],
        },
        "registration": {
            "fee": ctx["intro_fee"],
            "show_capacity": form_def.intro_show_capacity_on_page(),
            "capacity": (
                ctx["intro_capacity"] if form_def.intro_show_capacity_on_page() else None
            ),
            "seats_remaining": (
                ctx["intro_seats_remaining"]
                if form_def.intro_show_capacity_on_page()
                else None
            ),
        },
        "video": video or None,
        "brochure_url": ctx["intro_brochure_url"] or None,
        "apply_label": ctx["intro_apply_label"],
        "apply_url": ctx["apply_url"],
        "share_url": ctx["share_url"],
        "share_mailto": ctx["share_mailto"],
        "share_whatsapp": ctx["share_whatsapp"],
        "qrcode_url": ctx["intro_qrcode_url"],
        "closed": ctx["closed"],
        "can_apply": not ctx["closed"] and not ctx["studio_intro_preview"],
    }
