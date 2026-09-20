"""Build a Django Form class from stored FormField rows."""

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .field_validation import (
    apply_public_field_rules,
    text_max_length_for_field,
    textarea_max_length_for_field,
)
from .i18n_db import gettext_db
from .models import DISPLAY_ONLY_FIELD_TYPES, FieldType


def field_collects_answer(ff) -> bool:
    """True when the field expects a stored submission value."""
    return ff.field_type not in DISPLAY_ONLY_FIELD_TYPES


def raw_control_value(control_ff, post_data, files_data=None):
    """Normalize POST/FILES value for dependency checks (matches browser JS)."""
    key = f"f_{control_ff.pk}"
    files_data = files_data or {}
    if control_ff.field_type == FieldType.FILE:
        fobj = files_data.get(key)
        if fobj and getattr(fobj, "name", None):
            return str(fobj.name).strip()
        return ""
    if control_ff.field_type == FieldType.CHECKBOX:
        return "yes" if post_data.get(key) == "on" else ""
    if control_ff.field_type == FieldType.CHECKLIST:
        getlist = getattr(post_data, "getlist", None)
        if getlist:
            parts = [str(p).strip() for p in getlist(key) if str(p).strip()]
        else:
            parts = []
        return "\n".join(parts)
    v = post_data.get(key)
    if v is None:
        return ""
    return str(v).strip()


def field_is_visible(ff, post_data, files_data=None):
    ctl = ff.visibility_control_field
    if not ctl:
        return True
    allowed = ff.visibility_trigger_values()
    if not allowed:
        return False
    if ctl.field_type == FieldType.CHECKLIST:
        key = f"f_{ctl.pk}"
        getlist = getattr(post_data, "getlist", None)
        if getlist:
            selected = [str(p).strip() for p in getlist(key) if str(p).strip()]
        else:
            selected = []
        if not selected:
            return "" in allowed
        if any(s in allowed for s in selected):
            return True
        joined = "\n".join(selected)
        return joined in allowed
    current = raw_control_value(ctl, post_data, files_data)
    return current in allowed


def build_visibility_rules(fields_def):
    """Rules payload for client-side show/hide (JSON-serializable)."""
    rules = []
    for ff in fields_def:
        if ff.visibility_control_field_id:
            rules.append(
                {
                    "target": f"f_{ff.pk}",
                    "control": f"f_{ff.visibility_control_field.pk}",
                    "values": ff.visibility_trigger_values(),
                }
            )
    return rules


class DynamicPublicFormBase(forms.Form):
    """Adds conditional visibility validation for dependent fields."""

    def clean(self):
        cleaned_data = super().clean()
        post = getattr(self, "data", None) or {}
        files = getattr(self, "files", None) or {}
        fields_def = getattr(self.__class__, "_magicforms_fields_def", [])

        for ff in fields_def:
            if not field_collects_answer(ff):
                continue
            ctl = ff.visibility_control_field
            if not ctl:
                continue
            key = f"f_{ff.pk}"
            visible = field_is_visible(ff, post, files)

            if visible:
                if ff.required:
                    val = cleaned_data.get(key)
                    empty = val in (None, "") or (
                        ff.field_type == FieldType.CHECKBOX and not val
                    )
                    if ff.field_type == FieldType.CHECKLIST and not val:
                        empty = True
                    if ff.field_type == FieldType.FILE:
                        empty = not val
                    if empty:
                        msg = _("This field is required.")
                        if not any(str(e) == msg for e in self.errors.get(key, [])):
                            self.add_error(key, ValidationError(msg))
            else:
                if ff.field_type == FieldType.CHECKBOX:
                    cleaned_data[key] = False
                elif ff.field_type == FieldType.CHECKLIST:
                    cleaned_data[key] = []
                elif ff.field_type == FieldType.NUMBER:
                    cleaned_data[key] = None
                elif ff.field_type == FieldType.DATE:
                    cleaned_data[key] = None
                elif ff.field_type == FieldType.FILE:
                    cleaned_data[key] = None
                else:
                    cleaned_data[key] = ""

        for ff in fields_def:
            if not field_collects_answer(ff):
                continue
            apply_public_field_rules(
                self,
                ff,
                f"f_{ff.pk}",
                cleaned_data,
                post,
                files,
            )

        return cleaned_data


def build_public_form(form_model):
    """Returns a django.forms.Form subclass for GET/POST."""
    fields_def = list(form_model.get_ordered_fields())

    attrs: dict[str, forms.Field] = {}

    field_keys = []
    for ff in fields_def:
        if not field_collects_answer(ff):
            continue
        name = f"f_{ff.pk}"
        field_keys.append(name)
        has_dep = bool(ff.visibility_control_field_id)
        base_kw = {
            "label": gettext_db(ff.label),
            "required": False if has_dep else ff.required,
            "help_text": gettext_db(ff.help_text) if ff.help_text else "",
        }
        widget_attrs = {"class": "mf-input"}
        if ff.placeholder:
            widget_attrs["placeholder"] = gettext_db(ff.placeholder)

        if ff.field_type == FieldType.TEXT:
            attrs[name] = forms.CharField(
                max_length=text_max_length_for_field(ff),
                widget=forms.TextInput(attrs=widget_attrs),
                **base_kw,
            )
        elif ff.field_type == FieldType.TEXTAREA:
            ta_attrs = {"rows": 4, "class": "mf-input mf-input--textarea"}
            if ff.placeholder:
                ta_attrs["placeholder"] = gettext_db(ff.placeholder)
            attrs[name] = forms.CharField(
                max_length=textarea_max_length_for_field(ff),
                widget=forms.Textarea(attrs=ta_attrs),
                **base_kw,
            )
        elif ff.field_type == FieldType.EMAIL:
            attrs[name] = forms.EmailField(
                max_length=min(254, text_max_length_for_field(ff)),
                widget=forms.EmailInput(attrs=widget_attrs),
                **base_kw,
            )
        elif ff.field_type == FieldType.NUMBER:
            attrs[name] = forms.DecimalField(
                max_digits=18,
                decimal_places=6,
                required=(not has_dep and ff.required),
                widget=forms.NumberInput(attrs=widget_attrs),
                label=gettext_db(ff.label),
                help_text=base_kw["help_text"],
            )
        elif ff.field_type == FieldType.DATE:
            attrs[name] = forms.DateField(
                required=(not has_dep and ff.required),
                widget=forms.DateInput(attrs={"type": "date", **widget_attrs}),
                label=gettext_db(ff.label),
                help_text=base_kw["help_text"],
            )
        elif ff.field_type == FieldType.SELECT:
            choices = [(c, gettext_db(str(c))) for c in ff.choice_list()]
            if not choices:
                choices = [("", gettext_db("—"))]
            attrs[name] = forms.ChoiceField(
                choices=choices,
                widget=forms.Select(attrs={"class": "mf-input mf-input--select"}),
                **base_kw,
            )
        elif ff.field_type == FieldType.RADIO:
            choices = [(c, gettext_db(str(c))) for c in ff.choice_list()]
            attrs[name] = forms.ChoiceField(
                choices=choices,
                widget=forms.RadioSelect(attrs={"class": "mf-radio-group"}),
                **base_kw,
            )
        elif ff.field_type == FieldType.CHECKBOX:
            attrs[name] = forms.BooleanField(
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
                label=gettext_db(ff.label),
                help_text=base_kw["help_text"],
            )
        elif ff.field_type == FieldType.CHECKLIST:
            choices = [(c, gettext_db(str(c))) for c in ff.choice_list()]
            if not choices:
                choices = [("", gettext_db("—"))]
            attrs[name] = forms.MultipleChoiceField(
                choices=choices,
                widget=forms.CheckboxSelectMultiple(
                    attrs={"class": "mf-checklist-choices"}
                ),
                **base_kw,
            )
        elif ff.field_type == FieldType.FILE:
            attrs[name] = forms.FileField(
                required=(not has_dep and ff.required),
                widget=forms.FileInput(
                    attrs={
                        "class": "mf-input mf-input--file",
                        "accept": "*/*",
                    }
                ),
                label=gettext_db(ff.label),
                help_text=base_kw["help_text"],
            )
        else:
            attrs[name] = forms.CharField(
                max_length=500,
                widget=forms.TextInput(attrs=widget_attrs),
                **base_kw,
            )

    cls = type("DynamicPublicForm", (DynamicPublicFormBase,), attrs)
    cls._magicforms_fields_def = fields_def
    cls._magicforms_field_keys = field_keys
    return cls


def serialize_value(ff, raw):
    if ff.field_type == FieldType.CHECKBOX:
        return "yes" if raw else ""
    if ff.field_type == FieldType.CHECKLIST:
        if not raw:
            return ""
        if isinstance(raw, (list, tuple)):
            return "\n".join(str(x).strip() for x in raw if str(x).strip())
        return str(raw).strip()
    if ff.field_type == FieldType.FILE:
        if raw and getattr(raw, "name", None):
            return str(raw.name)
        return ""
    if raw is None:
        return ""
    return str(raw)
