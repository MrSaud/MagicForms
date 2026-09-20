"""Reverse public portal URLs for apex (``/e/…/``) and entity subdomains (``/f/…/``)."""

from django import template

from magicforms.subdomain import (
    on_portal_subdomain_urlconf,
    portal_absolute_uri,
    portal_reverse,
    studio_manage_url,
)

register = template.Library()


@register.simple_tag(takes_context=True)
def studio_manage_path(context, path):
    """``/manage/…`` on apex when the active urlconf has no ``manage:`` namespace."""
    request = context.get("request")
    if not path.startswith("/"):
        path = f"/{path}"
    if on_portal_subdomain_urlconf(request):
        return studio_manage_url(request, path)
    return path


@register.simple_tag(takes_context=True)
def portal_url(context, viewname, *args, **kwargs):
    request = context.get("request")
    return portal_reverse(request, viewname, args=args or None, kwargs=kwargs or None)


@register.simple_tag(takes_context=True)
def portal_full_url(context, viewname, *args, **kwargs):
    request = context.get("request")
    query = kwargs.pop("query", None)
    return portal_absolute_uri(
        request,
        viewname,
        args=args or None,
        query=query,
        **kwargs,
    )
