from django import template

from ..opaque_ids import encode

register = template.Library()


@register.filter(name="oid")
def oid(value):
    """``{{ obj.pk|oid }}``: opaque token for an id used in a query string or form value."""
    if value in (None, ""):
        return ""
    return encode(int(value))
