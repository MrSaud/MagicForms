"""Studio forms for pre-submit validation API configuration."""

from __future__ import annotations

import json
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Form, FormOutboundConfig, FormSubmitValidationConfig
from .outbound.crypto import encrypt_secret
from .outbound.url_validation import validate_outbound_endpoint_url

_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.0-9A-Z^_`a-z|~]+$")


class FormSubmitValidationConfigForm(forms.ModelForm):
    secret_plain = forms.CharField(
        label=_("API secret"),
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "mf-input", "autocomplete": "new-password", "placeholder": "••••••••"},
        ),
        help_text=_("Leave blank to keep the existing secret. Stored encrypted."),
    )

    class Meta:
        model = FormSubmitValidationConfig
        fields = (
            "is_active",
            "endpoint_url",
            "timeout_seconds",
            "auth_type",
            "auth_header_name",
            "hmac_header_name",
            "failure_action",
            "message_rejected",
            "message_unreachable",
            "message_error",
            "payload_root_key",
            "custom_headers_json",
        )
        labels = {
            "is_active": _("Active"),
            "endpoint_url": _("Validation endpoint URL"),
            "timeout_seconds": _("Timeout (seconds)"),
            "auth_type": _("Authentication"),
            "auth_header_name": _("Auth header name"),
            "hmac_header_name": _("HMAC signature header"),
            "failure_action": _("When validation fails"),
            "message_rejected": _("Message when API rejects (non-200)"),
            "message_unreachable": _("Message when API is unreachable"),
            "message_error": _("Message when validation request fails"),
            "payload_root_key": _("Payload root key"),
            "custom_headers_json": _("Custom headers (JSON object)"),
        }
        widgets = {
            "is_active": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "endpoint_url": forms.URLInput(
                attrs={"class": "mf-input", "placeholder": "https://api.example.com/validate"}
            ),
            "timeout_seconds": forms.NumberInput(attrs={"class": "mf-input", "min": 5, "max": 60}),
            "auth_type": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "auth_header_name": forms.TextInput(attrs={"class": "mf-input"}),
            "hmac_header_name": forms.TextInput(attrs={"class": "mf-input"}),
            "failure_action": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "message_rejected": forms.Textarea(
                attrs={"class": "mf-input", "rows": 3, "placeholder": ""},
            ),
            "message_unreachable": forms.Textarea(attrs={"class": "mf-input", "rows": 2}),
            "message_error": forms.Textarea(attrs={"class": "mf-input", "rows": 2}),
            "payload_root_key": forms.TextInput(attrs={"class": "mf-input"}),
            "custom_headers_json": forms.Textarea(
                attrs={"class": "mf-input", "rows": 3, "placeholder": '{"X-Tenant": "acme"}'}
            ),
        }
        help_texts = {
            "failure_action": _(
                "When the API does not return HTTP 200: block the submit, or let the respondent "
                "submit anyway after seeing a warning."
            ),
            "payload_root_key": _('Optional JSON wrapper key, e.g. "data".'),
            "message_rejected": _(
                "Optional. Placeholders: {{status}} (HTTP code), {{api_message}} (from API JSON: message, detail, error). "
                "Leave blank for the default English message."
            ),
            "message_unreachable": _("Optional. Leave blank for the default."),
            "message_error": _("Optional. Leave blank for the default."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["failure_action"].choices = [
            (
                FormSubmitValidationConfig.FailureAction.BLOCK,
                _("Block submit when the API does not return HTTP 200"),
            ),
            (
                FormSubmitValidationConfig.FailureAction.ALLOW_CONTINUE,
                _("Let the respondent choose to submit anyway"),
            ),
        ]
        self.fields["auth_type"].choices = [
            (FormOutboundConfig.AuthType.NONE, _("None")),
            (FormOutboundConfig.AuthType.BEARER, _("Bearer token")),
            (FormOutboundConfig.AuthType.HEADER, _("Custom header")),
            (FormOutboundConfig.AuthType.BASIC, _("Basic (secret is base64 user:pass or token)")),
            (FormOutboundConfig.AuthType.HMAC_SHA256, _("HMAC-SHA256 (secret + timestamp)")),
        ]
        if self.instance.pk and self.instance.has_secret():
            self.fields["secret_plain"].help_text = _("A secret is saved. Enter a new value only to replace it.")
        headers = self.instance.custom_headers_json if self.instance.pk else {}
        if isinstance(headers, dict) and headers:
            self.initial["custom_headers_json"] = json.dumps(headers, indent=2)

    def clean_endpoint_url(self):
        url = (self.cleaned_data.get("endpoint_url") or "").strip()
        if not url:
            return ""
        if self.cleaned_data.get("is_active"):
            return validate_outbound_endpoint_url(url)
        low = url.lower()
        if not (low.startswith("https://") or low.startswith("http://")):
            raise ValidationError(_("Use a full URL starting with https:// or http://."))
        return url

    def clean_auth_header_name(self):
        v = (self.cleaned_data.get("auth_header_name") or "").strip() or "Authorization"
        if len(v) > 64:
            raise ValidationError(_("Header name is too long."))
        if not _HEADER_NAME_RE.match(v):
            raise ValidationError(_("Use a valid HTTP header name."))
        return v

    def clean_custom_headers_json(self):
        raw = self.cleaned_data.get("custom_headers_json")
        if raw in (None, ""):
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValidationError(_("Invalid JSON.")) from exc
            if not isinstance(parsed, dict):
                raise ValidationError(_("Custom headers must be a JSON object."))
            return parsed
        raise ValidationError(_("Invalid custom headers."))

    def clean_message_rejected(self):
        return (self.cleaned_data.get("message_rejected") or "").strip()[
            : FormSubmitValidationConfig.MAX_APPLICANT_MESSAGE_LEN
        ]

    def clean_message_unreachable(self):
        return (self.cleaned_data.get("message_unreachable") or "").strip()[
            : FormSubmitValidationConfig.MAX_APPLICANT_MESSAGE_LEN
        ]

    def clean_message_error(self):
        return (self.cleaned_data.get("message_error") or "").strip()[
            : FormSubmitValidationConfig.MAX_APPLICANT_MESSAGE_LEN
        ]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_active"):
            if not (cleaned.get("endpoint_url") or "").strip():
                self.add_error("endpoint_url", ValidationError(_("Set the validation endpoint URL.")))
            auth = cleaned.get("auth_type")
            if auth != FormOutboundConfig.AuthType.NONE and not (
                (cleaned.get("secret_plain") or "").strip() or self.instance.has_secret()
            ):
                self.add_error("secret_plain", ValidationError(_("Set an API secret for this auth type.")))
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        plain = (self.cleaned_data.get("secret_plain") or "").strip()
        if plain:
            obj.secret_encrypted = encrypt_secret(plain)
        if commit:
            obj.save()
        return obj
