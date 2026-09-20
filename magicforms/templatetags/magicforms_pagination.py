from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def studio_page_url(context, page_number, anchor=""):
    """Build ``?page=…&per_page=…`` preserving other GET params; optional ``#anchor``."""
    request = context["request"]
    q = request.GET.copy()
    q["page"] = str(page_number)
    per_page = context.get("per_page")
    if per_page is not None:
        q["per_page"] = str(per_page)
    url = "?" + q.urlencode()
    fragment = (anchor or context.get("pagination_anchor") or "").strip().lstrip("#")
    if fragment:
        url += f"#{fragment}"
    return url


@register.simple_tag(takes_context=True)
def sample_forms_page_url(context, page_number):
    """Build ``?sample_page=…`` preserving other GET params (dashboard starter samples)."""
    request = context["request"]
    q = request.GET.copy()
    q["sample_page"] = str(page_number)
    return "?" + q.urlencode()
