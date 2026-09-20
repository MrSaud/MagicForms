"""Custom form widgets."""

from django import forms
from django.contrib.auth import get_user_model
from django.forms.utils import flatatt
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe


class AssignedUsersSelectWidget(forms.SelectMultiple):
    """
    Renders only currently selected <option>s (not the full staff list).
    Pair with Tom Select + /manage/api/users/search/ for searchable multi-select.
    """

    def __init__(self, search_url: str, attrs=None):
        super().__init__(attrs)
        self.search_url = search_url

    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = []
        elif not isinstance(value, (list, tuple)):
            value = [value]
        value = [str(v) for v in value if str(v)]

        final_attrs = self.build_attrs(self.attrs, attrs)
        final_attrs["name"] = name
        final_attrs["multiple"] = True
        final_attrs["data-search-url"] = self.search_url
        cls = (final_attrs.get("class") or "").strip()
        cls = f"{cls} js-workflow-assignees-ts".strip()
        final_attrs["class"] = cls
        if "id" not in final_attrs:
            final_attrs["id"] = "id_" + name

        users = []
        if value:
            users = list(
                get_user_model()
                .objects.filter(pk__in=value)
                .order_by("username")
            )

        option_bits = format_html_join(
            "",
            '<option value="{}" selected>{}</option>',
            ((u.pk, u.get_username()) for u in users),
        )
        return format_html(
            "<select{}>{}</select>",
            mark_safe(flatatt(final_attrs)),
            option_bits,
        )

    class Media:
        css = {
            "all": (
                "https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/css/tom-select.default.min.css",
            )
        }
        js = (
            "https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/js/tom-select.complete.min.js",
            "magicforms/js/workflow_assignees_tomselect.js",
        )


class SingleUserSearchSelectWidget(forms.Select):
    """
    One-person picker: empty until searched, matched by name or job title (see
    ``entity_users_for_entity_search`` / ``manage:user_search``). Dynamic-routing "route to"
    uses this instead of :class:`AssignedUsersSelectWidget`, which is multi-select.
    """

    def __init__(self, search_url: str, attrs=None):
        super().__init__(attrs)
        self.search_url = search_url

    def render(self, name, value, attrs=None, renderer=None):
        final_attrs = self.build_attrs(self.attrs, attrs)
        final_attrs["name"] = name
        final_attrs["data-search-url"] = self.search_url
        cls = (final_attrs.get("class") or "").strip()
        cls = f"{cls} js-route-to-ts".strip()
        final_attrs["class"] = cls
        if "id" not in final_attrs:
            final_attrs["id"] = "id_" + name

        selected_option = ""
        if value:
            user = get_user_model().objects.filter(pk=value).first()
            if user is not None:
                selected_option = format_html(
                    '<option value="{}" selected>{}</option>', user.pk, user.get_username()
                )
        return format_html(
            '<select{}><option value=""></option>{}</select>',
            mark_safe(flatatt(final_attrs)),
            selected_option,
        )

    class Media:
        css = {
            "all": (
                "https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/css/tom-select.default.min.css",
            )
        }
        js = (
            "https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/js/tom-select.complete.min.js",
            "magicforms/js/workflow_assignees_tomselect.js",
        )
