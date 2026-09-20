"""Studio forms for per-form outbound POST configuration."""

from __future__ import annotations

import json
import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from .models import FieldType, Form, FormField, FormOutboundConfig, FormOutboundFieldMap
from .outbound.crypto import encrypt_secret
from .outbound.applicant_data import applicant_attribute_catalog, applicant_attribute_keys
from .outbound.payload import SYSTEM_SOURCES
from .outbound.url_validation import validate_outbound_endpoint_url

_LOGIN_API_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.0-9A-Z^_`a-z|~]+$")


class FormOutboundConfigForm(forms.ModelForm):
    secret_plain = forms.CharField(
        label=_("API secret"),
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "mf-input", "autocomplete": "new-password", "placeholder": "••••••••"},
        ),
        help_text=_("Leave blank to keep the existing secret. Stored encrypted."),
    )

    class Meta:
        model = FormOutboundConfig
        fields = (
            "is_active",
            "endpoint_url",
            "timeout_seconds",
            "auth_type",
            "auth_header_name",
            "hmac_header_name",
            "trigger_submitted",
            "trigger_step_approved",
            "trigger_workflow_completed",
            "trigger_workflow_rejected",
            "payload_root_key",
            "custom_headers_json",
        )
        labels = {
            "is_active": _("Active"),
            "endpoint_url": _("Endpoint URL"),
            "timeout_seconds": _("Timeout (seconds)"),
            "auth_type": _("Authentication"),
            "auth_header_name": _("Auth header name"),
            "hmac_header_name": _("HMAC signature header"),
            "trigger_submitted": _("On form submit"),
            "trigger_step_approved": _("On step approved"),
            "trigger_workflow_completed": _("On workflow completed"),
            "trigger_workflow_rejected": _("On workflow rejected"),
            "payload_root_key": _("Payload root key"),
            "custom_headers_json": _("Custom headers (JSON object)"),
        }
        help_texts = {
            "endpoint_url": _("Full URL of your API endpoint."),
            "payload_root_key": _('Optional JSON wrapper key, e.g. "data".'),
        }
        widgets = {
            "is_active": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "endpoint_url": forms.URLInput(
                attrs={"class": "mf-input", "placeholder": "https://api.example.com/hooks/magicforms"}
            ),
            "timeout_seconds": forms.NumberInput(attrs={"class": "mf-input", "min": 5, "max": 60}),
            "auth_type": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "auth_header_name": forms.TextInput(attrs={"class": "mf-input"}),
            "hmac_header_name": forms.TextInput(attrs={"class": "mf-input"}),
            "trigger_submitted": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "trigger_step_approved": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "trigger_workflow_completed": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "trigger_workflow_rejected": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "payload_root_key": forms.TextInput(attrs={"class": "mf-input"}),
            "custom_headers_json": forms.Textarea(
                attrs={"class": "mf-input", "rows": 3, "placeholder": '{"X-Tenant": "acme"}'}
            ),
        }

    def __init__(self, *args, form_instance: Form | None = None, **kwargs):
        self._form_instance = form_instance
        super().__init__(*args, **kwargs)
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
        if not _LOGIN_API_HEADER_NAME_RE.match(v):
            raise ValidationError(_("Use a valid HTTP header name."))
        return v

    def clean_custom_headers_json(self):
        raw = self.cleaned_data.get("custom_headers_json")
        if raw in (None, ""):
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValidationError(_("Custom headers must be valid JSON object.")) from exc
            if not isinstance(parsed, dict):
                raise ValidationError(_("Custom headers must be a JSON object."))
            return parsed
        raise ValidationError(_("Custom headers must be a JSON object."))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_active"):
            if not (cleaned.get("endpoint_url") or "").strip():
                self.add_error("endpoint_url", ValidationError(_("Required when integration is active.")))
            auth = cleaned.get("auth_type")
            if auth and auth != FormOutboundConfig.AuthType.NONE:
                plain = (cleaned.get("secret_plain") or "").strip()
                if not plain and not (self.instance.pk and self.instance.has_secret()):
                    self.add_error(
                        "secret_plain",
                        ValidationError(_("Set an API secret for this auth type.")),
                    )
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        plain = (self.cleaned_data.get("secret_plain") or "").strip()
        if plain:
            obj.secret_encrypted = encrypt_secret(plain)
        if commit:
            obj.save()
        return obj


class FormOutboundFieldMapForm(forms.ModelForm):
    class Meta:
        model = FormOutboundFieldMap
        fields = (
            "external_key",
            "source_type",
            "source_ref",
            "transform",
            "required",
            "order",
        )
        labels = {
            "external_key": _("External JSON key"),
            "transform": _("Transform"),
            "required": _("Required in payload"),
        }
        widgets = {
            "external_key": forms.TextInput(attrs={"class": "mf-input"}),
            "source_type": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "source_ref": forms.TextInput(attrs={"class": "mf-input"}),
            "transform": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "required": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "order": forms.HiddenInput(),
        }

    def __init__(self, *args, form_fields=None, **kwargs):
        self._form_fields = form_fields or []
        super().__init__(*args, **kwargs)
        names = {ff.name for ff in self._form_fields}
        if self.instance.pk:
            st = self.instance.source_type
            ref = self.instance.source_ref or ""
            if st == FormOutboundFieldMap.SourceType.SYSTEM:
                self.initial["source_picker"] = f"system:{ref}"
            elif st == FormOutboundFieldMap.SourceType.APPLICANT:
                self.initial["source_picker"] = f"applicant:{ref}"
            elif st == FormOutboundFieldMap.SourceType.CONSTANT:
                self.initial["source_picker"] = f"constant:{ref}"
            elif ref in names:
                self.initial["source_picker"] = f"field:{ref}"

        form_choices = []
        for ff in self._form_fields:
            if ff.field_type == FieldType.FILE:
                form_choices.append((f"field:{ff.name}", f"{ff.label} ({ff.name}) · file"))
            else:
                form_choices.append((f"field:{ff.name}", f"{ff.label} ({ff.name})"))
        applicant_choices = [
            (f"applicant:{key}", label) for key, label in applicant_attribute_catalog()
        ]
        system_choices = [(f"system:{key}", key) for key in sorted(SYSTEM_SOURCES)]
        grouped = [("", [("", _("— Select source —"))])]
        if form_choices:
            grouped.append((_("Form answers"), form_choices))
        grouped.append((_("Applicant (submitter)"), applicant_choices))
        grouped.append((_("Submission & workflow"), system_choices))
        grouped.append((_("Other"), [("constant:", _("Constant value"))]))
        self.fields["source_picker"] = forms.ChoiceField(
            label=_("Source"),
            required=False,
            choices=grouped,
            widget=forms.Select(attrs={"class": "mf-input mf-input--select"}),
        )
        self.fields["source_ref"].label = _("Constant value / override")
        self.fields["source_ref"].required = False
        self.fields["source_type"].widget = forms.HiddenInput()
        self.fields["transform"].help_text = _(
            "For file fields: use “File: signed download URL”, “File: filename only”, or "
            "“File: object” (filename + URL + expiry). Default mapping uses the object."
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE"):
            return cleaned
        ext = (cleaned.get("external_key") or "").strip()
        if not ext:
            return cleaned
        picker = (cleaned.get("source_picker") or "").strip()
        if not picker:
            self.add_error("source_picker", ValidationError(_("Select a source for each mapped field.")))
            return cleaned
        if picker.startswith("field:"):
            cleaned["source_type"] = FormOutboundFieldMap.SourceType.FORM_FIELD
            cleaned["source_ref"] = picker[6:].strip()
        elif picker.startswith("applicant:"):
            cleaned["source_type"] = FormOutboundFieldMap.SourceType.APPLICANT
            cleaned["source_ref"] = picker[9:].strip()
            if cleaned["source_ref"] not in applicant_attribute_keys():
                self.add_error("source_picker", ValidationError(_("Unknown applicant field.")))
        elif picker.startswith("system:"):
            cleaned["source_type"] = FormOutboundFieldMap.SourceType.SYSTEM
            cleaned["source_ref"] = picker[7:].strip()
            if cleaned["source_ref"] not in SYSTEM_SOURCES:
                self.add_error("source_picker", ValidationError(_("Unknown system field.")))
        elif picker == "constant:":
            cleaned["source_type"] = FormOutboundFieldMap.SourceType.CONSTANT
            val = (cleaned.get("source_ref") or "").strip()
            if not val:
                self.add_error("source_ref", ValidationError(_("Enter the constant value.")))
            else:
                cleaned["source_ref"] = val
        else:
            self.add_error("source_picker", ValidationError(_("Invalid source.")))
        return cleaned


OUTBOUND_FIELD_MAP_MAX_NUM = 80

FormOutboundFieldMapFormSet = inlineformset_factory(
    FormOutboundConfig,
    FormOutboundFieldMap,
    form=FormOutboundFieldMapForm,
    extra=3,
    can_delete=True,
    max_num=OUTBOUND_FIELD_MAP_MAX_NUM,
)
