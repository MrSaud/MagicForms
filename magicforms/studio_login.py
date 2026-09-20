"""Studio sign-in: optional per-organization directory API; when it applies, directory auth only (no Django password fallback).

Superusers (``is_superuser``) always sign in with the Django password only—the directory API is not called and login data is not synced.
"""

from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django import forms
from django.utils.translation import gettext_lazy as _

from .login_api import entities_with_active_login_api, resolve_login_entity, try_directory_login_or_none
from .login_identity import parse_login_identity


def _directory_login_applies_to_username(username: str) -> bool:
    """Superusers always use Django password auth only (no directory API call or sync)."""
    uname = (username or "").strip()
    if not uname:
        return True
    User = get_user_model()
    return not User.objects.filter(username__iexact=uname, is_superuser=True).exists()


class StudioAuthenticationForm(AuthenticationForm):
    """Sign-in with organization username ``entity-slug-username`` (same as the mobile app)."""

    def __init__(self, request=None, get_params=None, *args, **kwargs):
        self._get_params = get_params if get_params is not None else {}
        self._parsed_entity_slug: str | None = None
        super().__init__(request, *args, **kwargs)
        self.fields["username"].label = _("Organization username")
        self.fields["username"].widget.attrs.update(
            {
                "class": "mf-input",
                "autocomplete": "username",
                "autofocus": True,
                "placeholder": "entity-slug-username",
            }
        )
        self.fields["username"].help_text = _(
            "Your organization slug, a hyphen, then your username (e.g. mosa-kuwait-jdoe)."
        )
        self.fields["password"].widget.attrs.update(
            {"class": "mf-input", "autocomplete": "current-password"}
        )
        self._api_entities = list(entities_with_active_login_api())

    def clean_username(self):
        raw = (self.cleaned_data.get("username") or "").strip()
        if not raw:
            raise forms.ValidationError(_("Enter your organization username (e.g. mosa-kuwait-jdoe)."))

        slugs = [e.slug for e in self._api_entities]
        parsed = parse_login_identity(raw, slugs)
        if not parsed.username:
            raise forms.ValidationError(_("Enter your organization username (e.g. mosa-kuwait-jdoe)."))

        if (
            len(self._api_entities) > 1
            and not parsed.entity_slug
            and _directory_login_applies_to_username(parsed.username)
        ):
            examples = ", ".join(f"{e.slug}-username" for e in self._api_entities[:2])
            raise forms.ValidationError(
                _("Include your organization slug before your username (e.g. %(examples)s).")
                % {"examples": examples}
            )

        self._parsed_entity_slug = parsed.entity_slug
        return parsed.username

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if self.errors or username is None or password is None:
            return self.cleaned_data

        username = username.strip()
        post_data = dict(self.data)
        if self._parsed_entity_slug:
            post_data["login_entity_slug"] = self._parsed_entity_slug
        entity = resolve_login_entity(post_data, self._get_params)
        if entity is not None and _directory_login_applies_to_username(username):
            user = try_directory_login_or_none(entity, username, password)
            if user is not None:
                self.confirm_login_allowed(user)
                user.backend = "magicforms.auth_backends.EntityDirectoryBackend"
                self.user_cache = user
                return self.cleaned_data
            raise forms.ValidationError(
                _(
                    "Directory sign-in failed: your organization’s API did not return success, or the "
                    "response was invalid. The endpoint must answer with HTTP 200 and JSON containing "
                    '"success": true (when present) and an "employee" or "user" object (e.g. username, '
                    "email, employee_number). When directory login is enabled "
                    "for this organization, the workspace does not fall back to the Django password."
                ),
                code="invalid_login",
            )

        self.user_cache = authenticate(self.request, username=username, password=password)
        if self.user_cache is None:
            raise self.get_invalid_login_error()
        self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class StudioLoginView(LoginView):
    template_name = "magicforms/manage/login.html"
    redirect_authenticated_user = True
    form_class = StudioAuthenticationForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["get_params"] = self.request.GET
        return kw

    def get_success_url(self):
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to
        from .subdomain import portal_origin_for_slug, subdomain_slug_detected

        slug = subdomain_slug_detected(self.request)
        if slug:
            return portal_origin_for_slug(slug, self.request).rstrip("/") + "/"
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["login_api_entities"] = list(entities_with_active_login_api())
        return ctx
