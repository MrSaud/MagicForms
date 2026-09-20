"""Configurable per-field validation for public submissions (configured in Studio)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

UNIQUE_VALUE_FIELD_TYPES = frozenset(
    {
        "text",
        "textarea",
        "email",
        "select",
        "radio",
        "number",
        "date",
    }
)


def validate_formfield_config(cleaned_data: dict) -> None:
    """Cross-check validation settings from StaffFieldForm.clean()."""
    errors: dict[str, ValidationError] = {}
    mn = cleaned_data.get("validation_min_length")
    mx = cleaned_data.get("validation_max_length")
    if mn is not None and mx is not None and mn > mx:
        errors["validation_max_length"] = ValidationError(
            _("Max length must be greater than or equal to min length."),
        )

    dmin = cleaned_data.get("validation_decimal_min")
    dmax = cleaned_data.get("validation_decimal_max")
    if dmin is not None and dmax is not None and dmin > dmax:
        errors["validation_decimal_max"] = ValidationError(
            _("Maximum must be greater than or equal to minimum."),
        )

    da = cleaned_data.get("validation_date_after")
    db = cleaned_data.get("validation_date_before")
    if da and db and da > db:
        errors["validation_date_before"] = ValidationError(
            _("“Not after” date must be on or after “Not before”.")
        )

    rx = (cleaned_data.get("validation_regex") or "").strip()
    if rx:
        try:
            re.compile(rx)
        except re.error as exc:
            errors["validation_regex"] = ValidationError(
                _("Invalid regular expression: %(err)s") % {"err": str(exc)},
            )

    if cleaned_data.get("validation_unique_value"):
        from .models import FieldType

        ft = (cleaned_data.get("field_type") or FieldType.TEXT).strip().lower()
        if ft not in UNIQUE_VALUE_FIELD_TYPES:
            errors["validation_unique_value"] = ValidationError(
                _(
                    "Unique value check applies to text, paragraph, email, dropdown, "
                    "radio, number, and date fields only."
                ),
            )

    if errors:
        raise ValidationError(errors)


def _field_has_error_code(form, key: str, code: str) -> bool:
    """True if ``form`` already has a field error with Django's validation ``code``."""
    if key not in form.errors:
        return False
    data = form.errors.as_data()
    if key not in data:
        return False
    return any(getattr(err, "code", None) == code for err in data[key])


def _field_has_error_message(form, key: str, message: str) -> bool:
    """Avoid adding the same validation message twice on one field."""
    if key not in form.errors:
        return False
    msg = str(message)
    return any(str(err) == msg for err in form.errors[key])


def _is_effectively_empty(ff, value) -> bool:
    from .models import FieldType

    if value is None or value == "":
        return True
    if ff.field_type == FieldType.CHECKBOX:
        return not value
    if ff.field_type == FieldType.CHECKLIST:
        return not value
    if ff.field_type == FieldType.FILE:
        return not value
    return False


def _apply_textlike_rules(form, ff, key: str, s: str) -> None:
    mn = ff.validation_min_length
    if mn is not None and len(s) < mn:
        msg = _("Enter at least %(n)d characters.") % {"n": mn}
        if not _field_has_error_code(form, key, "min_length") and not _field_has_error_message(
            form, key, msg
        ):
            form.add_error(key, ValidationError(msg))
    mx = ff.validation_max_length
    if mx is not None and len(s) > mx:
        msg = _("Enter at most %(n)d characters.") % {"n": mx}
        # CharField/EmailField already enforce ``max_length`` from Studio settings.
        if not _field_has_error_code(form, key, "max_length") and not _field_has_error_message(
            form, key, msg
        ):
            form.add_error(key, ValidationError(msg))
    needle = (ff.validation_must_contain or "").strip()
    if needle and needle.casefold() not in s.casefold():
        msg = _("This field must contain “%(text)s”.") % {"text": needle}
        if not _field_has_error_message(form, key, msg):
            form.add_error(key, ValidationError(msg))
    bad = (ff.validation_must_not_contain or "").strip()
    if bad and bad.casefold() in s.casefold():
        msg = _("This field must not contain “%(text)s”.") % {"text": bad}
        if not _field_has_error_message(form, key, msg):
            form.add_error(key, ValidationError(msg))
    eq_raw = (ff.validation_must_equal or "").strip()
    if eq_raw and s != eq_raw:
        msg = _("This field must exactly match the required value.")
        if not _field_has_error_message(form, key, msg):
            form.add_error(key, ValidationError(msg))
    rx = (ff.validation_regex or "").strip()
    if rx and not _field_has_error_code(form, key, "invalid"):
        try:
            cre = re.compile(rx)
        except re.error:
            return
        if not cre.search(s):
            msg = _("This value does not match the required pattern.")
            if not _field_has_error_message(form, key, msg):
                form.add_error(key, ValidationError(msg))


def _canonical_value_for_uniqueness(ff, value) -> str:
    from .dynamic_forms import serialize_value

    return (serialize_value(ff, value) or "").strip()


def submission_value_already_exists(ff, candidate: str, *, exclude_submission_id=None) -> bool:
    """True if another submission on the same form already saved this answer."""
    from .models import SubmissionValue

    if not candidate:
        return False

    qs = SubmissionValue.objects.filter(
        field_id=ff.pk,
        submission__form_id=ff.form_id,
    ).exclude(value="")
    if exclude_submission_id is not None:
        qs = qs.exclude(submission_id=exclude_submission_id)

    from .models import FieldType

    if ff.field_type == FieldType.EMAIL:
        target = candidate.strip().casefold()
        for existing in qs.values_list("value", flat=True):
            if existing.strip().casefold() == target:
                return True
        return False

    return qs.filter(value=candidate).exists()


def apply_public_field_rules(form, ff, key: str, cleaned_data: dict, post: dict, files) -> None:
    """Adds field errors based on optional FormField validation settings."""
    from .dynamic_forms import field_collects_answer, field_is_visible
    from .models import FieldType

    if not field_collects_answer(ff):
        return

    if not field_is_visible(ff, post, files):
        return

    value = cleaned_data.get(key)
    if _is_effectively_empty(ff, value):
        return

    ft = ff.field_type

    if ft in (
        FieldType.TEXT,
        FieldType.TEXTAREA,
        FieldType.EMAIL,
        FieldType.SELECT,
        FieldType.RADIO,
    ):
        s = str(value).strip()
        _apply_textlike_rules(form, ff, key, s)

    if ft == FieldType.NUMBER and value is not None:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return
        if ff.validation_integer_only and dec != dec.to_integral_value():
            msg = _("Enter a whole number (no decimals).")
            if not _field_has_error_message(form, key, msg):
                form.add_error(key, ValidationError(msg))
        dmin = ff.validation_decimal_min
        if dmin is not None and dec < dmin:
            msg = _("Enter a number greater than or equal to %(n)s.") % {"n": dmin}
            if not _field_has_error_message(form, key, msg):
                form.add_error(key, ValidationError(msg))
        dmax = ff.validation_decimal_max
        if dmax is not None and dec > dmax:
            msg = _("Enter a number less than or equal to %(n)s.") % {"n": dmax}
            if not _field_has_error_message(form, key, msg):
                form.add_error(key, ValidationError(msg))

    if ft == FieldType.DATE and value is not None:
        da = ff.validation_date_after
        if da and value < da:
            msg = _("Date must be on or after %(d)s.") % {"d": da}
            if not _field_has_error_message(form, key, msg):
                form.add_error(key, ValidationError(msg))
        db = ff.validation_date_before
        if db and value > db:
            msg = _("Date must be on or before %(d)s.") % {"d": db}
            if not _field_has_error_message(form, key, msg):
                form.add_error(key, ValidationError(msg))

    if getattr(ff, "validation_unique_value", False):
        canonical = _canonical_value_for_uniqueness(ff, cleaned_data.get(key))
        if canonical and submission_value_already_exists(ff, canonical):
            msg = _(
                "This value was already submitted on this form. "
                "Enter a different answer or contact the organization if you need help."
            )
            if not _field_has_error_message(form, key, msg):
                form.add_error(key, ValidationError(msg))


def text_max_length_for_field(ff) -> int:
    """Upper bound for CharField / email on the public form."""
    default = 500
    if ff.validation_max_length is not None:
        return max(1, min(int(ff.validation_max_length), 20000))
    return default


def textarea_max_length_for_field(ff) -> int:
    """Default cap for textarea when no validation max set (HTML/browser limit only)."""
    if ff.validation_max_length is not None:
        return max(1, min(int(ff.validation_max_length), 50000))
    return 10000
