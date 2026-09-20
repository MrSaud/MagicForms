import re

from django import forms
from .opaque_ids import encode as oid_encode
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import (
    DISPLAY_ONLY_FIELD_TYPES,
    EmployeeProfile,
    Entity,
    EntityEmailNotificationTemplate,
    EntityMembership,
    FieldType,
    Form,
    FormCategory,
    FormField,
    FormIntroSlide,
    FormLogo,
    FormSection,
    OptionsLayout,
    SubmissionAttachment,
    SupplementaryFormLink,
    UserSignature,
    WorkflowDelegation,
    WorkflowStep,
)
from .field_validation import validate_formfield_config
from .widgets import AssignedUsersSelectWidget, SingleUserSearchSelectWidget

User = get_user_model()

# HTTP field-name (token); https://www.rfc-editor.org/rfc/rfc9110#name-tokens
_LOGIN_API_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")


class StaffMetaForm(forms.ModelForm):
    class Meta:
        model = Form
        fields = (
            "entity",
            "title",
            "description",
            "layout_direction",
            "submission_deadline",
            "intro_capacity",
            "category",
            "print_template",
            "print_template_odt",
            "is_published",
            "one_time_submit",
            "is_for_public",
            "allow_submission_forward",
            "routing_mode",
            "hide_from_form_lists",
        )
        labels = {
            "entity": _("Organization"),
            "title": _("Title"),
            "description": _("Description"),
            "layout_direction": _("Default layout direction"),
            "submission_deadline": _("Submission deadline"),
            "intro_capacity": _("Capacity (seats)"),
            "category": _("Category"),
            "print_template": _("Print template (DOCX or PDF)"),
            "print_template_odt": _("Print template (ODT, optional)"),
            "is_published": _("Published"),
            "one_time_submit": _("One response per respondent"),
            "is_for_public": _("Allow access without signing in"),
            "allow_submission_forward": _("Allow forwarding submissions"),
            "routing_mode": _("Workflow routing"),
            "hide_from_form_lists": _("Hide from portal & home lists"),
        }
        help_texts = {
            "entity": _(
                "Which organization owns this form. Public links include the organization slug."
            ),
            "description": _(
                "Optional. Shown on the form hub and public form when filled in."
            ),
            "layout_direction": _(
                "Text direction of the public form pages. “Follow the site language” switches with the visitor's "
                "language; RTL or LTR pins the layout regardless of language."
            ),
            "print_template": _(
                "Optional primary template for merged documents. "
                "DOCX: Jinja placeholders like {{ field_name }} matching each field internal name "
                "(underscores; hyphens map to underscores; names starting with a digit get an f_ prefix, "
                "e.g. {{ f_1_copy }}). "
                "PDF: fillable AcroForm field names match internal slugs. "
                "Also: form_title, submitter_email, reference_token, submitted_at, current_step_label. "
                "Upload a separate ODT below if you want an editable LibreOffice copy for staff."
            ),
            "submission_deadline": _(
                "Optional. After this date (site time zone), the public form shows “closed” and does not accept POST."
            ),
            "intro_capacity": _("Optional maximum number of registrations for this form."),
            "category": _("Optional. Manage categories under Categories in the workspace nav."),
            "print_template_odt": _(
                "Optional LibreOffice copy for staff to download and edit. Answers are not merged into ODT; "
                "use the primary DOCX or PDF field above for merged filled outputs."
            ),
            "one_time_submit": _(
                "When on, signed-in users can submit only once. Visitors who are not signed in: "
                "once per browser after a successful submit."
            ),
            "is_for_public": _(
                "When on, anyone with the public link can open and submit without signing in. "
                "When off, the form is only for signed-in users (guests are redirected to log in)."
            ),
            "allow_submission_forward": _(
                "When on, staff and signed-in respondents can record that a submission was forwarded to another "
                "organization member (superusers may choose any active user). Adds a timeline entry; does not "
                "change workflow assignees."
            ),
            "routing_mode": _(
                "Fixed steps follow the ordered steps and assignees on the Workflow tab. Dynamic routing lets "
                "whoever is acting choose the next person by name or job title instead. Dynamic routing is "
                "being rolled out: forms set to it pause approve/reject until that engine ships. You can only "
                "change this while no submission is awaiting approval."
            ),
            "hide_from_form_lists": _(
                "When on, this form is hidden from the organization public portal, the global published directory, "
                "and the workspace home form list. Use for related-only or child forms that are opened from a "
                "parent flow. Direct URLs, QR codes, inbox, and this workspace page still work."
            ),
        }
        widgets = {
            "entity": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "title": forms.TextInput(attrs={"class": "mf-input"}),
            "description": forms.Textarea(
                attrs={"class": "mf-input mf-input--textarea", "rows": 4}
            ),
            "layout_direction": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "submission_deadline": forms.DateInput(
                attrs={"type": "date", "class": "mf-input"}
            ),
            "intro_capacity": forms.NumberInput(
                attrs={"class": "mf-input", "min": 1, "step": 1}
            ),
            "category": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "print_template": forms.FileInput(
                attrs={
                    "class": "mf-input mf-input--file",
                    "accept": (
                        ".docx,.pdf,"
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
                        "application/pdf"
                    ),
                }
            ),
            "print_template_odt": forms.FileInput(
                attrs={
                    "class": "mf-input mf-input--file",
                    "accept": ".odt,application/vnd.oasis.opendocument.text",
                }
            ),
            "is_published": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "one_time_submit": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "is_for_public": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "allow_submission_forward": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "routing_mode": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "hide_from_form_lists": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
        }

    def __init__(self, *args, staff_user=None, request=None, **kwargs):
        self.staff_user = staff_user
        self.request = request
        super().__init__(*args, **kwargs)
        from .entity_access import categories_queryset_for_user, entities_queryset_for_user

        ent_qs = (
            entities_queryset_for_user(staff_user, request=request)
            if staff_user is not None
            else Entity.objects.none()
        )
        self.fields["entity"].queryset = ent_qs
        if self.instance.pk and staff_user is not None and not staff_user.is_superuser:
            del self.fields["entity"]
        elif staff_user is not None and not staff_user.is_superuser:
            ids = list(ent_qs.values_list("pk", flat=True))
            if len(ids) == 1:
                self.fields["entity"].initial = ids[0]
                self.fields["entity"].widget = forms.HiddenInput()

        self.fields["category"].required = False
        self.fields["category"].queryset = (
            categories_queryset_for_user(staff_user, request=request)
            .select_related("entity")
            .order_by("entity__name", "order", "name")
            if staff_user is not None
            else FormCategory.objects.none()
        )
        self.fields["category"].empty_label = _("— No category —")
        self.fields["print_template_odt"].required = False

        from .i18n_db import gettext_db

        for name in ("entity", "category"):
            if name in self.fields:
                self.fields[name].label_from_instance = lambda obj, _gdb=gettext_db: _gdb(obj.name)

        file_hint = _("Choose a file to upload")
        for name in ("print_template", "print_template_odt"):
            if name in self.fields:
                w = self.fields[name].widget
                w.attrs.setdefault("title", file_hint)
                w.attrs.setdefault("aria-label", file_hint)

    def clean(self):
        cleaned = super().clean()
        entity = cleaned.get("entity")
        if entity is None and self.instance.pk:
            entity = self.instance.entity
        cat = cleaned.get("category")
        if cat and entity and cat.entity_id != entity.pk:
            raise ValidationError(
                {
                    "category": _(
                        "Choose a category from the same organization as the form, or leave category blank."
                    )
                }
            )
        new_routing_mode = cleaned.get("routing_mode")
        if (
            self.instance.pk
            and new_routing_mode
            and new_routing_mode != self.instance.routing_mode
        ):
            from .models import FormSubmission

            if FormSubmission.objects.filter(
                form_id=self.instance.pk,
                workflow_state=FormSubmission.WorkflowState.IN_PROGRESS,
            ).exists():
                raise ValidationError(
                    {
                        "routing_mode": _(
                            "This form has submissions awaiting approval. Wait until none are in progress "
                            "before changing workflow routing."
                        )
                    }
                )
        return cleaned

    def save(self, commit=True):
        if (
            self.staff_user is not None
            and not self.staff_user.is_superuser
            and not self.instance.pk
            and "entity" not in self.fields
        ):
            from .entity_access import entities_queryset_for_user

            ids = list(
                entities_queryset_for_user(self.staff_user, request=self.request).values_list("pk", flat=True)
            )
            if len(ids) == 1:
                self.instance.entity_id = ids[0]
        obj = super().save(commit=False)
        if obj.entity_id and not (obj.slug or "").strip():
            from .slug_utils import unique_form_slug

            obj.slug = unique_form_slug(obj.title, obj.entity, exclude_pk=obj.pk)
        if commit:
            obj.save()
        return obj


class StaffIntroPageForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["intro_venue_type"].choices = [
            ("", _("— Not specified —")),
            *list(Form.IntroVenueType.choices),
        ]
        for name in ("intro_event_start", "intro_event_end"):
            dt = getattr(self.instance, name, None)
            if dt:
                local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
                self.initial[name] = local.strftime("%Y-%m-%dT%H:%M")

    class Meta:
        model = Form
        fields = (
            "intro_page_enabled",
            "intro_title",
            "intro_subtitle",
            "intro_description",
            "intro_video_url",
            "intro_apply_button_label",
            "intro_venue_type",
            "intro_location",
            "intro_map_url",
            "intro_contact_name",
            "intro_contact_email",
            "intro_contact_phone",
            "intro_fee",
            "intro_show_capacity",
            "intro_event_start",
            "intro_event_end",
            "intro_details",
            "intro_details_list_style",
            "intro_attachment",
            "intro_rules",
            "intro_rules_list_style",
        )
        labels = {
            "intro_page_enabled": _("Show announcement page before applying"),
            "intro_title": _("Headline"),
            "intro_subtitle": _("Tagline"),
            "intro_description": _("Message"),
            "intro_video_url": _("Featured video URL"),
            "intro_apply_button_label": _("Apply button label"),
            "intro_venue_type": _("Format"),
            "intro_location": _("Venue or location"),
            "intro_map_url": _("Map link"),
            "intro_contact_name": _("Contact name"),
            "intro_contact_email": _("Contact email"),
            "intro_contact_phone": _("Contact phone"),
            "intro_fee": _("Registration fee"),
            "intro_show_capacity": _("Show remaining seats on announcement page"),
            "intro_event_start": _("Schedule starts"),
            "intro_event_end": _("Schedule ends"),
            "intro_details": _("Highlights"),
            "intro_details_list_style": _("Highlights list style"),
            "intro_attachment": _("Brochure (PDF)"),
            "intro_rules": _("Guidelines"),
            "intro_rules_list_style": _("Guidelines list style"),
        }
        help_texts = {
            "intro_page_enabled": _(
                "Optional. Off by default — applicants go straight to the form. "
                "When on, they see your announcement first."
            ),
            "intro_title": _("Optional. Defaults to the form title if blank."),
            "intro_subtitle": _("Optional short line under the headline."),
            "intro_description": _(
                "Optional. Plain text or simple HTML: <b>, <i>, <a href>, <ul><li>, <p>, <br>."
            ),
            "intro_video_url": _("Optional YouTube or Vimeo link."),
            "intro_apply_button_label": _('Optional, e.g. "Register now". Leave blank for "Apply now".'),
            "intro_venue_type": _("Optional. In person, online, or hybrid."),
            "intro_location": _("Optional address, room, or how to join online."),
            "intro_map_url": _("Optional Google Maps or directions link."),
            "intro_contact_name": _("Optional organizer or help desk name."),
            "intro_contact_email": _("Optional."),
            "intro_contact_phone": _("Optional."),
            "intro_fee": _('Optional, e.g. "Free" or "25 KWD".'),
            "intro_show_capacity": _(
                "When capacity is set in Form settings, show seats remaining on the announcement page. "
                "Has no effect if capacity is empty."
            ),
            "intro_event_start": _("Optional."),
            "intro_event_end": _("Optional. Must be after schedule start."),
            "intro_details": _("Optional. One highlight per line."),
            "intro_details_list_style": _("Bullet points or a numbered list on the announcement page."),
            "intro_attachment": _("Optional PDF brochure."),
            "intro_rules": _("Optional. One guideline per line."),
            "intro_rules_list_style": _("Bullet points or a numbered list on the announcement page."),
        }
        widgets = {
            "intro_page_enabled": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "intro_title": forms.TextInput(attrs={"class": "mf-input"}),
            "intro_subtitle": forms.TextInput(attrs={"class": "mf-input"}),
            "intro_description": forms.Textarea(
                attrs={"class": "mf-input mf-input--textarea", "rows": 6}
            ),
            "intro_video_url": forms.URLInput(attrs={"class": "mf-input", "placeholder": "https://"}),
            "intro_apply_button_label": forms.TextInput(attrs={"class": "mf-input"}),
            "intro_venue_type": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "intro_location": forms.TextInput(attrs={"class": "mf-input"}),
            "intro_map_url": forms.URLInput(attrs={"class": "mf-input", "placeholder": "https://"}),
            "intro_contact_name": forms.TextInput(attrs={"class": "mf-input"}),
            "intro_contact_email": forms.EmailInput(attrs={"class": "mf-input"}),
            "intro_contact_phone": forms.TextInput(attrs={"class": "mf-input"}),
            "intro_fee": forms.TextInput(attrs={"class": "mf-input"}),
            "intro_show_capacity": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "intro_details_list_style": forms.Select(
                attrs={"class": "mf-input mf-input--select"}
            ),
            "intro_details": forms.Textarea(
                attrs={"class": "mf-input mf-input--textarea", "rows": 6}
            ),
            "intro_attachment": forms.FileInput(
                attrs={"class": "mf-input mf-input--file", "accept": ".pdf,application/pdf"}
            ),
            "intro_event_start": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "mf-input"}
            ),
            "intro_event_end": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "mf-input"}
            ),
            "intro_rules_list_style": forms.Select(
                attrs={"class": "mf-input mf-input--select"}
            ),
            "intro_rules": forms.Textarea(
                attrs={"class": "mf-input mf-input--textarea", "rows": 5}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("intro_event_start")
        end = cleaned.get("intro_event_end")
        if start and end and end < start:
            raise ValidationError(
                {"intro_event_end": _("Schedule end must be after schedule start.")}
            )
        return cleaned


class StaffIntroSlideForm(forms.ModelForm):
    class Meta:
        model = FormIntroSlide
        fields = ("image", "caption")
        labels = {
            "image": _("Image"),
            "caption": _("Caption (optional)"),
        }
        help_texts = {
            "image": _(
                "PNG, JPEG, WebP, or GIF. Recommended 1920×1080 px (16:9). "
                "Other shapes are centered but may be cropped to fit the wide slideshow."
            ),
            "caption": _("Optional caption under the image."),
        }
        widgets = {
            "image": forms.FileInput(
                attrs={
                    "class": "mf-input mf-input--file",
                    "accept": ".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp",
                }
            ),
            "caption": forms.TextInput(attrs={"class": "mf-input"}),
        }


class StaffLogoForm(forms.ModelForm):
    """Create or edit a form header logo (image + left / center / right slot)."""

    def __init__(self, *args, form_instance=None, **kwargs):
        self.form_instance = form_instance
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["image"].required = False
        self.fields["header_slot"].widget.attrs.setdefault("class", "mf-input mf-input--select")

    class Meta:
        model = FormLogo
        fields = ("image", "header_slot")
        labels = {
            "header_slot": _("Position in header"),
        }
        help_texts = {
            "image": _(
                "PNG, JPEG, GIF, WebP, or SVG. Maximum three logos per form (one per position). "
                "For PNG, JPEG, and WebP, very light backgrounds are removed on upload (saved as PNG)."
            ),
            "header_slot": _(
                "Left and right sit beside the title column; center appears above the form title."
            ),
        }
        widgets = {
            "image": forms.FileInput(
                attrs={
                    "class": "mf-input mf-input--file",
                    "accept": "image/png,image/jpeg,image/gif,image/webp,image/svg+xml,.svg",
                }
            ),
        }

    def clean_header_slot(self):
        slot = self.cleaned_data.get("header_slot")
        if self.form_instance is None or slot is None:
            return slot
        qs = self.form_instance.logos.filter(header_slot=slot)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                _(
                    "Another logo already uses this position. Edit that logo or pick a different slot."
                )
            )
        return slot

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.sort_order = int(obj.header_slot)
        if commit:
            obj.save()
        return obj


class StaffEntityForm(forms.ModelForm):
    class Meta:
        model = Entity
        fields = (
            "name",
            "slug",
            "is_active",
            "page_logo",
            "public_site_title",
            "public_site_tagline",
            "home_news",
            "active_theme_index",
            "notifications_enabled",
            "email_notifications_enabled",
            "email_from_address",
            "email_reply_to",
            "email_smtp_host",
            "email_smtp_port",
            "email_smtp_use_tls",
            "email_smtp_use_ssl",
            "email_smtp_username",
            "email_smtp_password",
            "public_contact_email",
            "footer_note",
            "show_on_public_directory",
            "portal_meta_note",
            "login_api_endpoint",
            "login_api_tenant_id",
            "login_api_key_name",
            "login_api_token",
            "login_api_active",
        )
        labels = {
            "page_logo": _("Organization logo"),
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "mf-input"}),
            "slug": forms.TextInput(attrs={"class": "mf-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "page_logo": forms.FileInput(
                attrs={
                    "class": "mf-input mf-input--file",
                    "accept": "image/png,image/jpeg,image/gif,image/webp,image/svg+xml,.svg",
                }
            ),
            "public_site_title": forms.TextInput(attrs={"class": "mf-input"}),
            "public_site_tagline": forms.TextInput(attrs={"class": "mf-input"}),
            "home_news": forms.Textarea(attrs={"class": "mf-input mf-input--textarea", "rows": 6}),
            "notifications_enabled": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "email_notifications_enabled": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "email_from_address": forms.TextInput(
                attrs={
                    "class": "mf-input",
                    "placeholder": "HR Team <noreply@yourorg.com>",
                    "autocomplete": "off",
                }
            ),
            "email_reply_to": forms.EmailInput(attrs={"class": "mf-input", "autocomplete": "off"}),
            "email_smtp_host": forms.TextInput(
                attrs={"class": "mf-input", "placeholder": "smtp.yourorg.com", "autocomplete": "off"}
            ),
            "email_smtp_port": forms.NumberInput(
                attrs={"class": "mf-input", "min": "1", "max": "65535", "step": "1"}
            ),
            "email_smtp_use_tls": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "email_smtp_use_ssl": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "email_smtp_username": forms.TextInput(
                attrs={"class": "mf-input", "autocomplete": "off", "spellcheck": "false"}
            ),
            "email_smtp_password": forms.PasswordInput(
                attrs={"class": "mf-input", "autocomplete": "new-password"},
                render_value=False,
            ),
            "public_contact_email": forms.EmailInput(attrs={"class": "mf-input"}),
            "footer_note": forms.Textarea(attrs={"class": "mf-input mf-input--textarea", "rows": 3}),
            "show_on_public_directory": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "portal_meta_note": forms.Textarea(attrs={"class": "mf-input mf-input--textarea", "rows": 2}),
            "login_api_endpoint": forms.URLInput(
                attrs={
                    "class": "mf-input",
                    "placeholder": "https://directory.example.com/api/auth/login",
                    "autocomplete": "off",
                }
            ),
            "login_api_tenant_id": forms.NumberInput(
                attrs={
                    "class": "mf-input",
                    "placeholder": "1",
                    "min": "1",
                    "step": "1",
                    "autocomplete": "off",
                }
            ),
            "login_api_key_name": forms.TextInput(
                attrs={
                    "class": "mf-input",
                    "placeholder": "Authorization",
                    "autocomplete": "off",
                    "spellcheck": "false",
                }
            ),
            "login_api_token": forms.PasswordInput(
                attrs={"class": "mf-input", "autocomplete": "new-password", "placeholder": ""},
                render_value=False,
            ),
            "login_api_active": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
        }
        help_texts = {
            "page_logo": _(
                "Optional image for the workspace banner, public portal, and mobile app when users belong to this organization only. "
                "For PNG, JPEG, and WebP, very light backgrounds are removed on upload (saved as PNG). "
                "SVG and GIF are unchanged."
            ),
            "active_theme_index": _(
                "Visitors see only the selected theme on the public portal. The other two are saved for later."
            ),
            "login_api_endpoint": _(
                "Full URL (http:// or https://; prefer HTTPS in production) that accepts POST JSON "
                "{\"tenant_id\", \"username\", \"password\"} and returns HTTP 200 with JSON "
                "{\"success\": true, \"user\": { … }}. Typical user fields include samAccountName, "
                "userPrincipalName, displayName, givenName, surname, emailAddress, employeeId, department, "
                "title, office, telephoneNumber, and enabled."
            ),
            "login_api_tenant_id": _(
                "Integer tenant_id sent with every directory login request for this organization (not shown on the sign-in page)."
            ),
            "login_api_key_name": _(
                "HTTP header for the secret below. Blank or Authorization uses Bearer; any other name sends the raw token."
            ),
            "login_api_token": _(
                "API secret for the header above. Leave blank when editing to keep the current secret."
            ),
            "login_api_active": _(
                "When enabled, workspace sign-in for this organization uses only the directory API with the same "
                "username and password—no Django password fallback if the API rejects the credentials."
            ),
            "email_notifications_enabled": _(
                "When on (and Notifications enabled), all system email for this organization uses the SMTP settings below."
            ),
            "email_from_address": _(
                "Outgoing sender. Use a display name plus address, or email only."
            ),
            "email_smtp_password": _(
                "Leave blank when editing to keep the current SMTP password."
            ),
            "email_smtp_use_tls": _("Use STARTTLS (common on port 587)."),
            "email_smtp_use_ssl": _("Use implicit SSL (common on port 465). Disable STARTTLS when SSL is on."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .entity_theme import THEME_SLOT_COUNT, normalize_theme_presets

        active_initial = int(getattr(self.instance, "active_theme_index", 0) or 0)
        self.fields["active_theme_index"] = forms.TypedChoiceField(
            coerce=int,
            choices=[
                (0, _("Theme 1")),
                (1, _("Theme 2")),
                (2, _("Theme 3")),
            ],
            widget=forms.RadioSelect(),
            initial=active_initial,
            required=True,
            label=_("Active on public portal"),
            help_text=self.Meta.help_texts.get("active_theme_index", ""),
        )
        presets = normalize_theme_presets(getattr(self.instance, "theme_presets", None))
        hex_base = {
            "class": "mf-input mf-input--theme-hex",
            "maxlength": "7",
            "spellcheck": "false",
            "autocomplete": "off",
        }
        for i in range(THEME_SLOT_COUNT):
            slot = presets[i]
            self.fields[f"theme_slot_{i}_primary"] = forms.CharField(
                label=_("Primary color"),
                required=True,
                initial=slot["primary"],
                widget=forms.TextInput(attrs={**hex_base, "placeholder": "#0071e3"}),
            )
            self.fields[f"theme_slot_{i}_secondary"] = forms.CharField(
                label=_("Secondary accent"),
                required=False,
                initial=slot["secondary"],
                widget=forms.TextInput(attrs={**hex_base, "placeholder": "#optional"}),
            )
            self.fields[f"theme_slot_{i}_background"] = forms.CharField(
                label=_("Background tint"),
                required=False,
                initial=slot["background"],
                widget=forms.TextInput(attrs={**hex_base, "placeholder": "#f5f5f7"}),
            )

    def clean(self):
        cleaned = super().clean()
        from .entity_theme import HEX7, THEME_SLOT_COUNT, sanitize_hex7

        theme_errors = False
        presets: list[dict[str, str]] = []
        for i in range(THEME_SLOT_COUNT):
            p_key = f"theme_slot_{i}_primary"
            if p_key not in self.fields:
                continue
            p = sanitize_hex7(cleaned.get(p_key), "#0071e3")
            s_raw = (cleaned.get(f"theme_slot_{i}_secondary") or "").strip()
            s = sanitize_hex7(s_raw, p) if s_raw else ""
            bg_raw = (cleaned.get(f"theme_slot_{i}_background") or "").strip()
            if bg_raw and not HEX7.match(bg_raw):
                self.add_error(
                    f"theme_slot_{i}_background",
                    ValidationError(_("Use a full CSS hex color, e.g. #f5f5f7.")),
                )
                theme_errors = True
                bg = ""
            else:
                bg = bg_raw
            presets.append({"primary": p, "secondary": s, "background": bg})
        if not theme_errors:
            cleaned["_theme_presets"] = presets

        if cleaned.get("email_notifications_enabled"):
            from email.utils import parseaddr

            from_hdr = (cleaned.get("email_from_address") or "").strip()
            if not from_hdr:
                self.add_error(
                    "email_from_address",
                    ValidationError(_("Set a From address when email notifications are enabled.")),
                )
            else:
                _name, addr = parseaddr(from_hdr)
                if not addr or "@" not in addr:
                    self.add_error(
                        "email_from_address",
                        ValidationError(
                            _('Use a valid address, e.g. "Team <mail@yourorg.com>".')
                        ),
                    )
            if not (cleaned.get("email_smtp_host") or "").strip():
                self.add_error(
                    "email_smtp_host",
                    ValidationError(_("Set an SMTP host when email notifications are enabled.")),
                )
            port = cleaned.get("email_smtp_port")
            try:
                port_i = int(port) if port is not None else 0
            except (TypeError, ValueError):
                port_i = 0
            if port_i < 1 or port_i > 65535:
                self.add_error(
                    "email_smtp_port",
                    ValidationError(_("SMTP port must be between 1 and 65535.")),
                )
            if cleaned.get("email_smtp_use_tls") and cleaned.get("email_smtp_use_ssl"):
                self.add_error(
                    "email_smtp_use_ssl",
                    ValidationError(_("Choose either STARTTLS or SSL, not both.")),
                )
            user = (cleaned.get("email_smtp_username") or "").strip()
            pwd = (cleaned.get("email_smtp_password") or "").strip()
            if user and not pwd and not (
                self.instance.pk and (self.instance.email_smtp_password or "").strip()
            ):
                self.add_error(
                    "email_smtp_password",
                    ValidationError(_("Set an SMTP password when a username is provided.")),
                )

        if cleaned.get("login_api_active"):
            ep = (cleaned.get("login_api_endpoint") or "").strip()
            if not ep:
                self.add_error(
                    "login_api_endpoint",
                    ValidationError(_("Set the directory API URL when directory login is active.")),
                )
            tid = cleaned.get("login_api_tenant_id")
            if tid is None:
                self.add_error(
                    "login_api_tenant_id",
                    ValidationError(_("Set the tenant ID when directory login is active.")),
                )
            tok = (cleaned.get("login_api_token") or "").strip()
            if not tok and not (self.instance.pk and (self.instance.login_api_token or "").strip()):
                self.add_error(
                    "login_api_token",
                    ValidationError(_("Set an API secret when directory login is active.")),
                )
        return cleaned

    def clean_login_api_key_name(self):
        v = (self.cleaned_data.get("login_api_key_name") or "").strip()
        if not v:
            return ""
        if len(v) > 64:
            raise ValidationError(_("Header name is too long (max 64 characters)."))
        if not _LOGIN_API_HEADER_NAME_RE.match(v):
            raise ValidationError(
                _("Use a valid HTTP header name (letters, digits, hyphen, and !#$&'*+.^_`|~).")
            )
        return v

    def clean_login_api_endpoint(self):
        url = (self.cleaned_data.get("login_api_endpoint") or "").strip()
        if not url:
            return ""
        low = url.lower()
        if not (low.startswith("https://") or low.startswith("http://")):
            raise ValidationError(_("Use a full URL starting with http:// or https://."))
        return url

    def clean_login_api_tenant_id(self):
        tid = self.cleaned_data.get("login_api_tenant_id")
        if tid in (None, ""):
            return None
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            raise ValidationError(_("Enter a whole-number tenant ID."))
        if tid < 1:
            raise ValidationError(_("Tenant ID must be at least 1."))
        return tid

    def save(self, commit=True):
        obj = super().save(commit=False)
        tp = self.cleaned_data.get("_theme_presets")
        if tp is not None:
            obj.theme_presets = tp
        new_tok = (self.cleaned_data.get("login_api_token") or "").strip()
        if new_tok:
            obj.login_api_token = new_tok
        elif self.instance.pk and (self.instance.login_api_token or "").strip():
            obj.login_api_token = self.instance.login_api_token
        new_smtp_pwd = (self.cleaned_data.get("email_smtp_password") or "").strip()
        if new_smtp_pwd:
            obj.email_smtp_password = new_smtp_pwd
        elif self.instance.pk and (self.instance.email_smtp_password or "").strip():
            obj.email_smtp_password = self.instance.email_smtp_password
        if commit:
            obj.save()
        return obj


class StaffCategoryForm(forms.ModelForm):
    class Meta:
        model = FormCategory
        fields = ("entity", "name", "order")
        widgets = {
            "entity": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "name": forms.TextInput(attrs={"class": "mf-input", "placeholder": "e.g. Finance"}),
            "order": forms.NumberInput(attrs={"class": "mf-input", "min": 0}),
        }

    def __init__(self, *args, staff_user=None, request=None, **kwargs):
        self.staff_user = staff_user
        self.request = request
        super().__init__(*args, **kwargs)
        from .entity_access import entities_queryset_for_user

        ent_qs = (
            entities_queryset_for_user(staff_user, request=request)
            if staff_user is not None
            else Entity.objects.none()
        )
        self.fields["entity"].queryset = ent_qs
        if staff_user is not None and not staff_user.is_superuser:
            ids = list(ent_qs.values_list("pk", flat=True))
            if len(ids) == 1:
                self.fields["entity"].initial = ids[0]
                self.fields["entity"].widget = forms.HiddenInput()

    def save(self, commit=True):
        if (
            self.staff_user is not None
            and not self.staff_user.is_superuser
            and not self.instance.pk
            and "entity" not in self.fields
        ):
            from .entity_access import entities_queryset_for_user

            ids = list(
                entities_queryset_for_user(self.staff_user, request=self.request).values_list("pk", flat=True)
            )
            if len(ids) == 1:
                self.instance.entity_id = ids[0]
        return super().save(commit=commit)


def _resolved_field_type_for_staff_field(form):
    if form.is_bound:
        return (form.data.get("field_type") or "").strip().lower()
    if form.instance.pk:
        return str(form.instance.field_type).strip().lower()
    init = form.fields["field_type"].initial
    return str(init or FieldType.TEXT).strip().lower()


def _field_type_needs_choices(ft):
    return ft in ("select", "radio", "checklist")


def _field_type_needs_options_layout(ft):
    return ft in ("radio", "checklist")


def _is_display_only_field_type(ft):
    return (ft or "").strip().lower() in DISPLAY_ONLY_FIELD_TYPES


def _configure_break_staff_field(form):
    for name in list(form.fields):
        if name.startswith("validation_"):
            form.fields.pop(name, None)
    for name in ("required", "inline", "label", "hint", "placeholder", "mapping_key", "help_text"):
        if name not in form.fields:
            continue
        fld = form.fields[name]
        fld.required = False
        if name == "label":
            fld.initial = fld.initial or "Break"
        elif name == "inline":
            fld.initial = False
        else:
            fld.initial = ""
        fld.widget = forms.HiddenInput()


def _configure_display_only_staff_field(form, ft):
    for name in list(form.fields):
        if name.startswith("validation_"):
            form.fields.pop(name, None)
    if "required" in form.fields:
        fld = form.fields["required"]
        fld.required = False
        fld.initial = False
        fld.widget = forms.HiddenInput()
    if "inline" in form.fields:
        if ft == FieldType.LABEL:
            form.fields["inline"].help_text = _(
                "Show this text on the same row as other inline fields."
            )
        else:
            form.fields["inline"].help_text = _(
                "Show this information block on the same row as other inline fields."
            )
    for name in ("placeholder", "mapping_key", "help_text"):
        if name in form.fields:
            fld = form.fields[name]
            fld.required = False
            fld.initial = ""
            fld.widget = forms.HiddenInput()
    if "hint" in form.fields:
        form.fields["hint"].widget.attrs.setdefault("rows", 5)
    if "label" in form.fields:
        if ft == FieldType.LABEL:
            form.fields["label"].required = True
            form.fields["label"].help_text = _(
                "Text shown on the live form (no answer is collected)."
            )
            form.fields["hint"].help_text = _("Optional extra text below the label.")
        else:
            form.fields["label"].required = False
            form.fields["label"].help_text = _("Optional heading above the hint text.")


class StaffFieldForm(forms.ModelForm):
    class Meta:
        model = FormField
        fields = (
            "field_type",
            "mapping_key",
            "label",
            "required",
            "inline",
            "hint",
            "help_text",
            "placeholder",
            "section",
            "choices_text",
            "options_layout",
            "visibility_control_field",
            "visibility_show_when_values",
            "validation_min_length",
            "validation_max_length",
            "validation_must_contain",
            "validation_must_not_contain",
            "validation_must_equal",
            "validation_regex",
            "validation_integer_only",
            "validation_decimal_min",
            "validation_decimal_max",
            "validation_date_after",
            "validation_date_before",
            "validation_unique_value",
        )
        widgets = {
            "field_type": forms.Select(
                attrs={
                    "class": "mf-input mf-input--select",
                    "data-mf-choices-toggle": "1",
                }
            ),
            "mapping_key": forms.TextInput(
                attrs={
                    "class": "mf-input",
                    "placeholder": "e.g. email, job_title",
                    "autocomplete": "off",
                }
            ),
            "label": forms.TextInput(attrs={"class": "mf-input"}),
            "required": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "inline": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "section": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "hint": forms.Textarea(
                attrs={
                    "class": "mf-input mf-input--textarea",
                    "rows": 3,
                    "placeholder": _("Shown under the label on the live form"),
                }
            ),
            "help_text": forms.TextInput(attrs={"class": "mf-input"}),
            "placeholder": forms.TextInput(attrs={"class": "mf-input"}),
            "choices_text": forms.Textarea(
                attrs={
                    "class": "mf-input mf-input--textarea",
                    "rows": 5,
                    "placeholder": "One option per line",
                }
            ),
            "options_layout": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "visibility_control_field": forms.Select(
                attrs={"class": "mf-input mf-input--select"}
            ),
            "visibility_show_when_values": forms.Textarea(
                attrs={
                    "class": "mf-input mf-input--textarea",
                    "rows": 4,
                    "placeholder": "One matching value per line (exact match after trim)",
                }
            ),
            "validation_min_length": forms.NumberInput(
                attrs={"class": "mf-input", "min": 0, "placeholder": _("e.g. 5")},
            ),
            "validation_max_length": forms.NumberInput(
                attrs={"class": "mf-input", "min": 1, "placeholder": _("e.g. 200")},
            ),
            "validation_must_contain": forms.TextInput(
                attrs={"class": "mf-input", "placeholder": _('e.g. "@company"')},
            ),
            "validation_must_not_contain": forms.TextInput(
                attrs={"class": "mf-input", "placeholder": _("Forbidden substring")},
            ),
            "validation_must_equal": forms.TextInput(
                attrs={"class": "mf-input", "placeholder": _("Exact required value")},
            ),
            "validation_regex": forms.TextInput(
                attrs={"class": "mf-input", "placeholder": "^[A-Za-z]+$"},
            ),
            "validation_integer_only": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "validation_decimal_min": forms.NumberInput(
                attrs={"class": "mf-input", "step": "any", "placeholder": _("Min number")},
            ),
            "validation_decimal_max": forms.NumberInput(
                attrs={"class": "mf-input", "step": "any", "placeholder": _("Max number")},
            ),
            "validation_date_after": forms.DateInput(
                attrs={"type": "date", "class": "mf-input"},
            ),
            "validation_date_before": forms.DateInput(
                attrs={"type": "date", "class": "mf-input"},
            ),
            "validation_unique_value": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
        }
        labels = {
            "hint": _("Hint"),
            "help_text": _("Helper text (below input)"),
        }
        help_texts = {
            "hint": _(
                "Optional guidance under the label. For display-only fields (label or hint types), "
                "hint text is shown on the live form and no answer is collected."
            ),
            "help_text": _("Short note shown below the input on the live form."),
            "options_layout": _(
                "For radio buttons and checklist: show each choice in a horizontal row or a vertical column."
            ),
            "validation_min_length": _(
                "Text-like fields only. Empty = no minimum. Submitted text is trimmed before counting."
            ),
            "validation_max_length": _(
                "Caps length on the public form. Empty = defaults (short text/email/paragraph)."
            ),
            "validation_must_contain": _("Case-insensitive substring that must appear."),
            "validation_must_not_contain": _("Case-insensitive substring that must not appear."),
            "validation_must_equal": _(
                "If set, the answer must equal this exact string (after trimming). Rare; use sparingly."
            ),
            "validation_regex": _("Python regular expression tested against the full string (search)."),
            "validation_integer_only": _("Numbers only: reject values with a decimal point."),
            "validation_decimal_min": _("Minimum numeric value (inclusive)."),
            "validation_decimal_max": _("Maximum numeric value (inclusive)."),
            "validation_date_after": _("Earliest allowed date (inclusive)."),
            "validation_date_before": _("Latest allowed date (inclusive)."),
            "validation_unique_value": _(
                "Block submit when another response on this form already used the same answer "
                "(e.g. ID number or email). Applies to text-like, number, and date fields."
            ),
        }

    def __init__(self, *args, form_instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._form = form_instance
        self.fields["field_type"].choices = FieldType.choices
        self.fields["visibility_control_field"].required = False
        self.fields["visibility_control_field"].empty_label = _("— None —")
        self.fields["section"].required = False
        self.fields["section"].empty_label = _("— No section —")
        if form_instance:
            qs = FormField.objects.filter(form=form_instance).order_by("order", "id")
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields["visibility_control_field"].queryset = qs.exclude(
                field_type__in=DISPLAY_ONLY_FIELD_TYPES
            )
            self.fields["section"].queryset = FormSection.objects.filter(form=form_instance).order_by(
                "order", "id"
            )
        else:
            self.fields["section"].queryset = FormSection.objects.none()

        ft = _resolved_field_type_for_staff_field(self)
        if not _field_type_needs_choices(ft):
            self.fields.pop("choices_text", None)
        if not _field_type_needs_options_layout(ft):
            self.fields.pop("options_layout", None)
        elif "options_layout" in self.fields:
            self.fields["options_layout"].choices = OptionsLayout.choices
        if ft == FieldType.BREAK:
            _configure_break_staff_field(self)
        elif _is_display_only_field_type(ft):
            _configure_display_only_staff_field(self, ft)
        elif "label" in self.fields:
            self.fields["label"].help_text = _("Shown to respondents as the field label.")

    def clean(self):
        cleaned = super().clean()
        ctl = cleaned.get("visibility_control_field")
        vals_raw = (cleaned.get("visibility_show_when_values") or "").strip()
        if ctl:
            if not vals_raw:
                raise ValidationError(
                    {
                        "visibility_show_when_values": _(
                            "Enter at least one value that shows this field."
                        )
                    }
                )
            if self.instance.pk and ctl.pk == self.instance.pk:
                raise ValidationError(
                    {"visibility_control_field": _("A field cannot depend on itself.")}
                )
        elif vals_raw:
            raise ValidationError(
                {
                    "visibility_control_field": _(
                        "Pick a control field or remove trigger values."
                    ),
                }
            )
        validate_formfield_config(cleaned)
        ft = (cleaned.get("field_type") or "").strip().lower()
        if ft == FieldType.BREAK:
            cleaned["required"] = False
            cleaned["inline"] = False
            cleaned["placeholder"] = ""
            cleaned["mapping_key"] = ""
            cleaned["help_text"] = ""
            cleaned["hint"] = ""
            if not (cleaned.get("label") or "").strip():
                cleaned["label"] = "Break"
        elif ft == FieldType.LABEL:
            cleaned["required"] = False
            cleaned["placeholder"] = ""
            cleaned["mapping_key"] = ""
            cleaned["help_text"] = ""
            if not (cleaned.get("label") or "").strip():
                raise ValidationError(
                    {
                        "label": _("Enter the text to display."),
                    },
                )
        elif ft == FieldType.HINT:
            cleaned["required"] = False
            cleaned["placeholder"] = ""
            cleaned["mapping_key"] = ""
            cleaned["help_text"] = ""
            label = (cleaned.get("label") or "").strip()
            hint_body = (cleaned.get("hint") or "").strip()
            if not label and not hint_body:
                raise ValidationError(
                    {
                        "hint": _(
                            "Enter hint text or a heading (label) for this information block."
                        ),
                    },
                )
            if not label:
                cleaned["label"] = hint_body[:255]
        if ft == FieldType.CHECKLIST:
            if not (cleaned.get("choices_text") or "").strip():
                raise ValidationError(
                    {
                        "choices_text": _(
                            "Add at least one checklist item (one per line)."
                        ),
                    },
                )
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if str(obj.field_type or "").strip().lower() in DISPLAY_ONLY_FIELD_TYPES:
            obj.required = False
            obj.placeholder = ""
            obj.mapping_key = ""
            obj.help_text = ""
        if str(obj.field_type or "").strip().lower() == FieldType.BREAK:
            obj.inline = False
            obj.hint = ""
            if not (obj.label or "").strip():
                obj.label = "Break"
        form = self._form or getattr(obj, "form", None)
        if form and not (obj.name or "").strip():
            from .slug_utils import unique_form_field_name

            base = (obj.label or "").strip() or "field"
            obj.name = unique_form_field_name(base, form, exclude_pk=obj.pk)
        if commit:
            obj.save()
        return obj


class StaffSectionForm(forms.ModelForm):
    class Meta:
        model = FormSection
        fields = ("title", "description", "starts_collapsed")
        widgets = {
            "title": forms.TextInput(attrs={"class": "mf-input"}),
            "description": forms.Textarea(
                attrs={"class": "mf-input mf-input--textarea", "rows": 3}
            ),
            "starts_collapsed": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
        }


class StaffWorkflowForm(forms.ModelForm):
    class Meta:
        model = WorkflowStep
        fields = ("label", "description", "assigned_users")
        help_texts = {
            "assigned_users": _(
                "Users in this form’s organization (staff and non-staff). Type to search by username, email, or name."
            ),
        }
        widgets = {
            "label": forms.TextInput(attrs={"class": "mf-input"}),
            "description": forms.Textarea(
                attrs={"class": "mf-input mf-input--textarea", "rows": 3}
            ),
        }

    def __init__(self, *args, form_instance=None, **kwargs):
        self._form_instance = form_instance
        super().__init__(*args, **kwargs)
        from .entity_access import entity_users_for_entity

        User = get_user_model()
        self.fields["assigned_users"].required = False
        search_url = reverse("manage:user_search")
        if form_instance and form_instance.entity_id:
            self.fields["assigned_users"].queryset = entity_users_for_entity(form_instance.entity_id)
            search_url = f"{search_url}?form={oid_encode(form_instance.pk)}&scope=entity"
        else:
            self.fields["assigned_users"].queryset = User.objects.filter(is_active=True).order_by("username")
        self.fields["assigned_users"].widget = AssignedUsersSelectWidget(
            search_url=search_url,
            attrs={"class": "mf-input"},
        )

    def save(self, commit=True):
        obj = super().save(commit=False)
        form = self._form_instance
        if form and form.pk and not (obj.slug or "").strip():
            from .slug_utils import unique_workflow_step_slug

            obj.slug = unique_workflow_step_slug(obj.label, form, exclude_pk=obj.pk)
        if commit:
            obj.save()
            self.save_m2m()
        return obj

    def clean_assigned_users(self):
        users = self.cleaned_data.get("assigned_users")
        if not users or not self._form_instance or not self._form_instance.entity_id:
            return users
        from .models import EntityMembership

        allowed = set(
            EntityMembership.objects.filter(entity_id=self._form_instance.entity_id).values_list(
                "user_id", flat=True
            )
        )
        bad = [u for u in users if u.pk not in allowed or not u.is_active]
        if bad:
            raise ValidationError(_("Each assignee must be an active member of this form’s organization."))
        return users


_mf_input = {"class": "mf-input"}
_mf_textarea = {"class": "mf-input mf-input--textarea", "rows": 3}
_mf_select = {"class": "mf-input mf-input--select"}


class StaffUserCreateForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs=_mf_input))

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name", "is_staff")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("username", "email", "first_name", "last_name"):
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("class", "mf-input")
        self.fields["password1"].widget.attrs.setdefault("class", "mf-input")
        self.fields["password2"].widget.attrs.setdefault("class", "mf-input")
        self.fields["is_staff"].widget.attrs.setdefault("class", "mf-checkbox")
        self.fields["is_staff"].label = _("Organization admin")
        self.fields["is_staff"].help_text = _(
            "Organization admins can use builder tools, People, and other org management in the workspace "
            "when they belong to at least one organization. End users (unchecked) are applicants with a "
            "lighter portal. The Django admin site at /admin/ is only for super admins."
        )


class StaffUserAccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "is_staff", "is_active")
        widgets = {
            "username": forms.TextInput(attrs=_mf_input),
            "email": forms.EmailInput(attrs=_mf_input),
            "first_name": forms.TextInput(attrs=_mf_input),
            "last_name": forms.TextInput(attrs=_mf_input),
            "is_staff": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
            "is_active": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "is_staff" in self.fields:
            self.fields["is_staff"].label = _("Organization admin")
            self.fields["is_staff"].help_text = _(
                "Organization admins get builder and org management in the workspace with organization "
                "membership. End users use the applicant portal. /admin/ remains super-admin-only."
            )


class StaffOptionalPasswordForm(forms.Form):
    password1 = forms.CharField(
        label=_("New password"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={**_mf_input, "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label=_("New password (again)"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={**_mf_input, "autocomplete": "new-password"}),
    )

    def clean(self):
        data = super().clean()
        p1 = data.get("password1") or ""
        p2 = data.get("password2") or ""
        if p1 or p2:
            if p1 != p2:
                raise ValidationError(_("The two password fields do not match."))
        return data


class StaffWorkflowDelegationForm(forms.ModelForm):
    class Meta:
        model = WorkflowDelegation
        fields = ("entity", "delegator", "delegate", "valid_from", "valid_until", "notes", "is_active")
        widgets = {
            "entity": forms.Select(attrs=_mf_select),
            "delegator": forms.Select(attrs=_mf_select),
            "delegate": forms.Select(attrs=_mf_select),
            "valid_from": forms.DateInput(attrs={**_mf_input, "type": "date"}),
            "valid_until": forms.DateInput(attrs={**_mf_input, "type": "date"}),
            "notes": forms.TextInput(attrs=_mf_input),
            "is_active": forms.CheckboxInput(attrs={"class": "mf-checkbox"}),
        }

    def __init__(self, *args, staff_user=None, request=None, **kwargs):
        self.staff_user = staff_user
        self.request = request
        super().__init__(*args, **kwargs)
        from .entity_access import (
            effective_entity_ids,
            entities_queryset_for_user,
            entity_users_for_entity,
        )

        User = get_user_model()
        ent_qs = (
            entities_queryset_for_user(staff_user, request=request)
            if staff_user is not None
            else Entity.objects.none()
        )
        self.fields["entity"].queryset = ent_qs
        if staff_user is not None and not staff_user.is_superuser:
            ids = list(ent_qs.values_list("pk", flat=True))
            if len(ids) == 1:
                self.fields["entity"].initial = ids[0]
                self.fields["entity"].widget = forms.HiddenInput()
                members = entity_users_for_entity(ids[0])
            else:
                from .models import EntityMembership

                uids = (
                    EntityMembership.objects.filter(entity_id__in=ids)
                    .values_list("user_id", flat=True)
                    .distinct()
                )
                members = User.objects.filter(pk__in=uids, is_active=True).order_by("username")
        else:
            if staff_user is not None and request is not None:
                eids = effective_entity_ids(staff_user, request)
                if eids is not None:
                    from .models import EntityMembership

                    uids = (
                        EntityMembership.objects.filter(entity_id__in=eids)
                        .values_list("user_id", flat=True)
                        .distinct()
                    )
                    members = User.objects.filter(pk__in=uids, is_active=True).order_by("username")
                else:
                    members = User.objects.filter(is_active=True).order_by("username")
            else:
                members = User.objects.filter(is_active=True).order_by("username")
        self.fields["delegator"].queryset = members
        self.fields["delegate"].queryset = members
        self.fields["delegator"].label = _("Delegator (assignee covered)")
        self.fields["delegate"].label = _("Delegate (acts on their behalf)")
        self.fields["valid_from"].required = False
        self.fields["valid_until"].required = False
        self.fields["notes"].required = False
        self.fields["is_active"].initial = True

    def clean(self):
        from .models import EntityMembership

        data = super().clean()
        entity = data.get("entity")
        delegator = data.get("delegator")
        delegate = data.get("delegate")
        if delegator and delegate and delegator.pk == delegate.pk:
            raise ValidationError(_("Delegator and delegate must be different users."))
        if entity and delegator and not EntityMembership.objects.filter(entity=entity, user=delegator).exists():
            raise ValidationError(
                {"delegator": _("This user is not a member of the selected organization.")}
            )
        if entity and delegate and not EntityMembership.objects.filter(entity=entity, user=delegate).exists():
            raise ValidationError(
                {"delegate": _("This user is not a member of the selected organization.")}
            )
        if delegator and delegate and data.get("is_active", True):
            qs = WorkflowDelegation.objects.filter(
                entity=entity,
                delegator=delegator,
                delegate=delegate,
                is_active=True,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    _(
                        "An active delegation already exists for this pair in this organization."
                    )
                )
        vf = data.get("valid_from")
        vu = data.get("valid_until")
        if vf and vu and vf > vu:
            raise ValidationError(_("“Valid from” must be on or before “valid until”."))
        return data

    def save(self, commit=True):
        if (
            self.staff_user is not None
            and not self.staff_user.is_superuser
            and not self.instance.pk
            and "entity" not in self.fields
        ):
            from .entity_access import entities_queryset_for_user

            ids = list(
                entities_queryset_for_user(self.staff_user, request=self.request).values_list("pk", flat=True)
            )
            if len(ids) == 1:
                self.instance.entity_id = ids[0]
        return super().save(commit=commit)


class StaffEmployeeProfileForm(forms.ModelForm):
    class Meta:
        model = EmployeeProfile
        exclude = ("user", "created_at", "updated_at")
        widgets = {
            "employee_number": forms.TextInput(attrs=_mf_input),
            "civil_id": forms.TextInput(attrs=_mf_input),
            "job_title": forms.TextInput(attrs=_mf_input),
            "department": forms.TextInput(attrs=_mf_input),
            "birth_date": forms.DateInput(attrs={**_mf_input, "type": "date"}),
            "hire_date": forms.DateInput(attrs={**_mf_input, "type": "date"}),
            "degree": forms.TextInput(attrs=_mf_input),
            "field_of_study": forms.TextInput(attrs=_mf_input),
            "employment_type": forms.Select(attrs=_mf_select),
            "gender": forms.Select(attrs=_mf_select),
            "nationality": forms.TextInput(attrs=_mf_input),
            "work_phone": forms.TextInput(attrs=_mf_input),
            "mobile_phone": forms.TextInput(attrs=_mf_input),
            "work_email": forms.EmailInput(attrs=_mf_input),
            "office_location": forms.TextInput(attrs=_mf_input),
            "manager": forms.Select(attrs=_mf_select),
            "emergency_contact_name": forms.TextInput(attrs=_mf_input),
            "emergency_contact_phone": forms.TextInput(attrs=_mf_input),
            "notes": forms.Textarea(attrs={**_mf_textarea, "rows": 4}),
        }

    def __init__(self, *args, manager_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if manager_queryset is not None and "manager" in self.fields:
            self.fields["manager"].queryset = manager_queryset
            self.fields["manager"].required = False
            self.fields["manager"].label = _("Manager")


class StaffUserSignatureForm(forms.ModelForm):
    class Meta:
        model = UserSignature
        fields = ("label", "image")
        widgets = {
            "label": forms.TextInput(attrs=_mf_input),
            "image": forms.FileInput(
                attrs={
                    "class": "mf-input mf-input--file",
                    "accept": "image/png,image/jpeg,image/jpg,image/gif,image/webp,image/svg+xml,.png,.jpg,.jpeg,.gif,.webp,.svg",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["label"].required = False
        self.fields["image"].help_text = _(
            "PNG, JPEG, GIF, WebP, or SVG. You can add many signatures per user. "
            "For PNG, JPEG, and WebP, very light backgrounds are removed automatically (stored as PNG). "
            "SVG and GIF are not altered."
        )


class StaffSubmissionAttachmentForm(forms.ModelForm):
    """Upload an extra document on a submission (public track page or manage)."""

    class Meta:
        model = SubmissionAttachment
        fields = ("title", "file")
        widgets = {
            "title": forms.TextInput(attrs=_mf_input),
            "file": forms.FileInput(
                attrs={
                    "class": "mf-input mf-input--file",
                    "accept": ".pdf,.doc,.docx,.odt,.png,.jpg,.jpeg,.gif,.webp,.txt,.csv,.xlsx,.xls",
                }
            ),
        }

    def __init__(self, *args, submission=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._submission = submission
        self.fields["title"].required = False
        self.fields["file"].help_text = _(
            "PDF, Word, images, spreadsheet, or text. Max one file per upload; "
            "up to %(max)d attachments per submission, %(mb)d MB each."
        ) % {
            "max": SubmissionAttachment.MAX_PER_SUBMISSION,
            "mb": SubmissionAttachment.MAX_FILE_BYTES // (1024 * 1024),
        }

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if f is not None and getattr(f, "size", 0) > SubmissionAttachment.MAX_FILE_BYTES:
            raise ValidationError(
                _("File must be %(mb)d MB or smaller.")
                % {"mb": SubmissionAttachment.MAX_FILE_BYTES // (1024 * 1024)},
            )
        return f

    def clean(self):
        data = super().clean()
        sub = self._submission
        if sub is not None and not self.instance.pk:
            if sub.document_attachments.count() >= SubmissionAttachment.MAX_PER_SUBMISSION:
                raise ValidationError(
                    _("This submission already has the maximum of %(max)d attachments.")
                    % {"max": SubmissionAttachment.MAX_PER_SUBMISSION},
                )
        return data


class StaffSubmissionApplicantEmailForm(forms.Form):
    """Send an email to the applicant from the submission manage page."""

    to_email = forms.EmailField(
        label=_("To"),
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "mf-input",
                "autocomplete": "email",
                "placeholder": "applicant@example.com",
            }
        ),
    )
    subject = forms.CharField(
        label=_("Subject"),
        max_length=200,
        widget=forms.TextInput(attrs={"class": "mf-input"}),
    )
    message = forms.CharField(
        label=_("Message"),
        max_length=8000,
        widget=forms.Textarea(
            attrs={
                "class": "mf-input mf-input--textarea",
                "rows": 6,
                "placeholder": _("Write your message to the applicant…"),
            }
        ),
    )

    def __init__(self, *args, submission=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.submission = submission


class StaffSubmissionForwardForm(forms.Form):
    """Record forwarding of a submission to another user (timeline event)."""

    target_user = forms.ModelChoiceField(
        label=_("Forward to"),
        queryset=User.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": "mf-input mf-input--select"}),
    )
    note = forms.CharField(
        label=_("Optional note"),
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"class": "mf-input mf-input--textarea", "rows": 2}),
    )

    def __init__(self, *args, actor, form_entity_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(is_active=True).order_by("username")
        if not actor.is_superuser:
            uids = EntityMembership.objects.filter(entity_id=form_entity_id).values_list(
                "user_id", flat=True
            )
            qs = qs.filter(pk__in=uids)
        qs = qs.exclude(pk=actor.pk)
        self.fields["target_user"].queryset = qs


class StaffSubmissionRouteForm(forms.Form):
    """
    Dynamic routing: approve by choosing exactly one person (by name or job title) to receive
    the submission next, mark it complete, or reject it back to the original submitter.
    """

    ACTION_ROUTE = "route"
    ACTION_COMPLETE = "complete"
    ACTION_REJECT = "reject"
    ACTION_CHOICES = (
        (ACTION_ROUTE, _("Route to")),
        (ACTION_COMPLETE, _("Mark complete")),
        (ACTION_REJECT, _("Reject")),
    )

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    target_user = forms.ModelChoiceField(
        label=_("Route to"),
        queryset=User.objects.none(),
        required=False,
        widget=SingleUserSearchSelectWidget(search_url=""),
    )
    stage_label = forms.CharField(
        label=_("Stage (optional)"),
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": "mf-input", "placeholder": _("e.g. Finance review")}
        ),
    )
    comment = forms.CharField(
        label=_("Note"),
        required=False,
        max_length=800,
        widget=forms.Textarea(attrs={"class": "mf-input mf-input--textarea", "rows": 2}),
    )

    def __init__(self, *args, actor, form_entity_id, search_url, **kwargs):
        super().__init__(*args, **kwargs)
        # Always scoped to the submission's own organization, even for superusers: routing changes
        # who can see and act on this submission, unlike the lighter-weight "forward" note.
        uids = EntityMembership.objects.filter(entity_id=form_entity_id).values_list(
            "user_id", flat=True
        )
        qs = User.objects.filter(pk__in=uids, is_active=True).exclude(pk=actor.pk).order_by("username")
        self.fields["target_user"].queryset = qs
        self.fields["target_user"].widget.search_url = search_url

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("action")
        if action == self.ACTION_ROUTE and not cleaned.get("target_user"):
            self.add_error("target_user", _("Choose who this goes to next."))
        if action == self.ACTION_REJECT and not (cleaned.get("comment") or "").strip():
            self.add_error("comment", _("Enter a reason for rejection before submitting."))
        return cleaned


class StaffRelatedFormLinkForm(forms.ModelForm):
    """Attach a related (child) form to this parent; invitations when the submission reaches a workflow step."""

    class Meta:
        model = SupplementaryFormLink
        fields = ("child_form", "trigger_step")
        widgets = {
            "child_form": forms.Select(attrs={"class": "mf-input mf-input--select"}),
            "trigger_step": forms.Select(attrs={"class": "mf-input mf-input--select"}),
        }

    def __init__(self, *args, parent_form=None, **kwargs):
        self.parent_form = parent_form
        super().__init__(*args, **kwargs)
        if parent_form is None:
            return
        self.fields["child_form"].queryset = (
            Form.objects.filter(entity_id=parent_form.entity_id, deleted_at__isnull=True)
            .exclude(pk=parent_form.pk)
            .order_by("title")
        )
        self.fields["trigger_step"].queryset = parent_form.workflow_steps.order_by("order", "id")
        self.fields["child_form"].label = _("Related form")
        self.fields["trigger_step"].label = _("When submission reaches this step")

    def clean(self):
        cleaned = super().clean()
        cf = cleaned.get("child_form")
        ts = cleaned.get("trigger_step")
        if self.parent_form and cf and ts:
            qs = SupplementaryFormLink.objects.filter(
                parent_form=self.parent_form,
                child_form=cf,
                trigger_step=ts,
            )
            if qs.exists():
                raise ValidationError(
                    _("A related link for this form and step already exists."),
                )
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.parent_form = self.parent_form
        obj.full_clean()
        if commit:
            obj.save()
        return obj


class EntityEmailNotificationsManageForm(forms.Form):
    """Per-organization automatic email templates and toggles."""

    notify_on_submit = forms.BooleanField(
        label=_("Send email when a form is submitted"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    notify_on_accept = forms.BooleanField(
        label=_("Send email when workflow is completed (accepted)"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    notify_on_reject = forms.BooleanField(
        label=_("Send email when workflow is rejected"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    notify_on_step_approved = forms.BooleanField(
        label=_("Send email on each intermediate approval step"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    staff_contact_use_template = forms.BooleanField(
        label=_("Prefill manual “Email applicant” with staff contact template"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, entity, *args, **kwargs):
        from magicforms.notification_emails import (
            ensure_entity_notification_defaults,
            get_notification_template,
        )

        self.entity = entity
        ensure_entity_notification_defaults(entity)
        behavior = entity.email_notification_behavior
        initial = kwargs.pop("initial", {})
        initial.setdefault("notify_on_submit", behavior.notify_on_submit)
        initial.setdefault("notify_on_accept", behavior.notify_on_accept)
        initial.setdefault("notify_on_reject", behavior.notify_on_reject)
        initial.setdefault("notify_on_step_approved", behavior.notify_on_step_approved)
        initial.setdefault("staff_contact_use_template", behavior.staff_contact_use_template)
        for kind, _label in EntityEmailNotificationTemplate.Kind.choices:
            tpl = get_notification_template(entity, kind)
            initial.setdefault(f"tpl_{kind}_active", tpl.is_active)
            initial.setdefault(f"tpl_{kind}_subject", tpl.subject)
            initial.setdefault(f"tpl_{kind}_body", tpl.body)
        super().__init__(*args, initial=initial, **kwargs)

        textarea = forms.Textarea(attrs={"class": "form-control", "rows": 8})
        subject_widget = forms.TextInput(attrs={"class": "form-control"})
        for kind, label in EntityEmailNotificationTemplate.Kind.choices:
            self.fields[f"tpl_{kind}_active"] = forms.BooleanField(
                label=_("Active"),
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
            )
            self.fields[f"tpl_{kind}_subject"] = forms.CharField(
                label=_("Subject"),
                max_length=200,
                widget=subject_widget,
            )
            self.fields[f"tpl_{kind}_body"] = forms.CharField(
                label=_("Body"),
                widget=textarea,
            )

    def save(self):
        from magicforms.models import (
            EntityEmailNotificationBehavior,
            EntityEmailNotificationTemplate,
        )

        behavior, _ = EntityEmailNotificationBehavior.objects.get_or_create(entity=self.entity)
        behavior.notify_on_submit = self.cleaned_data["notify_on_submit"]
        behavior.notify_on_accept = self.cleaned_data["notify_on_accept"]
        behavior.notify_on_reject = self.cleaned_data["notify_on_reject"]
        behavior.notify_on_step_approved = self.cleaned_data["notify_on_step_approved"]
        behavior.staff_contact_use_template = self.cleaned_data["staff_contact_use_template"]
        behavior.save()

        for kind, _label in EntityEmailNotificationTemplate.Kind.choices:
            tpl, _ = EntityEmailNotificationTemplate.objects.get_or_create(
                entity=self.entity,
                kind=kind,
            )
            tpl.is_active = self.cleaned_data[f"tpl_{kind}_active"]
            tpl.subject = self.cleaned_data[f"tpl_{kind}_subject"].strip()
            tpl.body = self.cleaned_data[f"tpl_{kind}_body"].strip()
            tpl.save()
        return behavior
