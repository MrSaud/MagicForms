import re
import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import get_valid_filename, slugify
from django.utils.translation import gettext_lazy as _

from .entity_theme import default_theme_presets


class Entity(models.Model):
    """Tenant / organization. Only Django superusers may create or edit entities in the workspace."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=80, unique=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    page_logo = models.FileField(
        "Organization logo",
        upload_to="entity_page_logos/%Y/%m/",
        max_length=500,
        blank=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "svg"],
            )
        ],
        help_text="Optional image for the workspace banner, public portal, mobile app, and directory card. "
        "For PNG, JPEG, and WebP uploads, very light backgrounds are removed automatically (stored as PNG). "
        "SVG and GIF are not altered.",
    )
    public_site_title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Browser tab and portal header. Leave blank to use the organization name.",
    )
    public_site_tagline = models.CharField(
        max_length=400,
        blank=True,
        help_text="Short line under the title on the public portal.",
    )
    home_news = models.TextField(
        "Home / portal news",
        blank=True,
        help_text="News or announcements for the public portal (plain text; line breaks are kept).",
    )
    theme_presets = models.JSONField(
        default=default_theme_presets,
        help_text="Up to three portal color sets; each entry has primary, secondary, and background (hex strings).",
    )
    active_theme_index = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(2)],
        help_text="Which of the three presets is applied on the public portal (0–2).",
    )
    notifications_enabled = models.BooleanField(
        "Notifications enabled",
        default=True,
        help_text="When off, automated notifications (including email) for this organization are skipped.",
    )
    email_notifications_enabled = models.BooleanField(
        "Email notifications enabled",
        default=False,
        help_text="When on, all outbound email for this organization uses the SMTP settings below (workspace applicant mail and future notification hooks).",
    )
    email_from_address = models.CharField(
        "Email From address",
        max_length=254,
        blank=True,
        help_text='Sender for outbound mail, e.g. "HR Team <noreply@yourorg.com>" or plain email@yourorg.com.',
    )
    email_reply_to = models.EmailField(
        "Default Reply-To",
        blank=True,
        help_text="Optional default Reply-To on applicant emails (staff user email is also added when set).",
    )
    email_smtp_host = models.CharField("SMTP host", max_length=255, blank=True)
    email_smtp_port = models.PositiveIntegerField(
        "SMTP port",
        default=587,
        help_text="Usually 587 (STARTTLS) or 465 (SSL).",
    )
    email_smtp_use_tls = models.BooleanField(
        "SMTP use TLS (STARTTLS)",
        default=True,
        help_text="Typical for port 587. Turn off when using SSL on port 465.",
    )
    email_smtp_use_ssl = models.BooleanField(
        "SMTP use SSL",
        default=False,
        help_text="Typical for port 465. Do not enable together with STARTTLS.",
    )
    email_smtp_username = models.CharField("SMTP username", max_length=255, blank=True)
    email_smtp_password = models.CharField(
        "SMTP password",
        max_length=512,
        blank=True,
        help_text="Stored on the organization record. Leave blank when editing to keep the current password.",
    )
    public_contact_email = models.EmailField(
        "Public contact email",
        blank=True,
        help_text="Optional contact shown on the public portal.",
    )
    footer_note = models.TextField(
        max_length=2000,
        blank=True,
        help_text="Small print or disclaimer at the bottom of the public portal.",
    )
    show_on_public_directory = models.BooleanField(
        default=True,
        help_text="List this organization on the global home page directory.",
    )
    portal_meta_note = models.CharField(
        max_length=500,
        blank=True,
        help_text="Internal note (not shown publicly); e.g. billing reference or launch checklist.",
    )
    login_api_endpoint = models.URLField(
        "Directory login API URL",
        max_length=500,
        blank=True,
        help_text="Full URL of the directory login API (http:// or https://; JSON: tenant_id, username, password). "
        "Prefer HTTPS in production.",
    )
    login_api_tenant_id = models.PositiveIntegerField(
        "Directory login tenant ID",
        null=True,
        blank=True,
        help_text="tenant_id sent in the directory login API JSON body for this organization.",
    )
    login_api_key_name = models.CharField(
        "API key name",
        max_length=64,
        blank=True,
        help_text="HTTP header for the API secret. Blank uses Authorization with a Bearer token; "
        "e.g. X-API-Key sends the raw secret in that header.",
    )
    login_api_token = models.CharField(
        "Directory login API token",
        max_length=512,
        blank=True,
        help_text="Secret sent in the header named above (Bearer prefix only when the header is Authorization).",
    )
    login_api_active = models.BooleanField(
        "Directory login API active",
        default=False,
        help_text="When on, workspace sign-in for this organization uses only the directory API (no Django password fallback on failure).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Entities"

    def __str__(self):
        return self.name

    def get_public_display_title(self) -> str:
        t = (self.public_site_title or "").strip()
        return t or self.name

    def get_portal_absolute_url(self, request=None) -> str:
        from .subdomain import entity_portal_base_url

        return entity_portal_base_url(self, request)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        logo_included = update_fields is None or "page_logo" in update_fields
        if (
            logo_included
            and self.page_logo
            and hasattr(self.page_logo, "_committed")
            and not self.page_logo._committed
        ):
            from .logo_processing import maybe_replace_image_field_with_knockout_png

            maybe_replace_image_field_with_knockout_png(self.page_logo)
        super().save(*args, **kwargs)


class EntityEmailNotificationBehavior(models.Model):
    """Per-organization toggles for automated applicant email."""

    entity = models.OneToOneField(
        Entity,
        on_delete=models.CASCADE,
        related_name="email_notification_behavior",
    )
    notify_on_submit = models.BooleanField(
        "Email applicant when form is submitted",
        default=True,
    )
    notify_on_accept = models.BooleanField(
        "Email applicant when workflow is completed (accepted)",
        default=True,
    )
    notify_on_reject = models.BooleanField(
        "Email applicant when workflow is rejected",
        default=True,
    )
    notify_on_step_approved = models.BooleanField(
        "Email applicant on each intermediate approval step",
        default=False,
    )
    staff_contact_use_template = models.BooleanField(
        "Prefill “Email applicant” with staff contact template",
        default=True,
    )

    class Meta:
        verbose_name = "Email notification behavior"
        verbose_name_plural = "Email notification behaviors"

    def __str__(self):
        return f"Email behavior · {self.entity_id}"


class EntityEmailNotificationTemplate(models.Model):
    """Editable subject/body for applicant emails (placeholders supported)."""

    class Kind(models.TextChoices):
        SUBMITTED = "submitted", "Form submitted"
        ACCEPTED = "accepted", "Workflow accepted (completed)"
        REJECTED = "rejected", "Workflow rejected"
        STAFF_CONTACT = "staff_contact", "Staff contact (manual email)"

    MAX_SUBJECT_LEN = 200
    MAX_BODY_LEN = 8000

    entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="email_notification_templates",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices, db_index=True)
    subject = models.CharField(max_length=MAX_SUBJECT_LEN)
    body = models.TextField()
    is_active = models.BooleanField(default=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "kind"],
                name="uniq_mf_entity_email_template_entity_kind",
            ),
        ]
        ordering = ["entity_id", "kind"]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.entity_id}"


class EntityMembership(models.Model):
    """Links a user to an entity they may work in (forms, inbox, delegations are scoped by membership)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="entity_memberships",
    )
    entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    manage_people_read = models.BooleanField(default=False)
    manage_people_write = models.BooleanField(default=False)
    manage_forms_read = models.BooleanField(default=False)
    manage_forms_write = models.BooleanField(default=False)
    view_responses_read = models.BooleanField(default=False)
    view_responses_write = models.BooleanField(default=False)
    export_responses_read = models.BooleanField(default=False)
    export_responses_write = models.BooleanField(default=False)
    manage_delegations_read = models.BooleanField(default=False)
    manage_delegations_write = models.BooleanField(default=False)
    manage_categories_read = models.BooleanField(default=False)
    manage_categories_write = models.BooleanField(default=False)
    manage_entity_settings_read = models.BooleanField(default=False)
    manage_entity_settings_write = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "entity"], name="uniq_entity_membership_user_entity"),
        ]
        ordering = ["entity__name", "user__username"]

    def __str__(self):
        return f"{self.user_id} @ {self.entity_id}"


class FormCategory(models.Model):
    """Staff-defined bucket for forms (e.g. HR, Finance), scoped to one entity."""

    entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, db_index=True, blank=True)
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "Form categories"
        constraints = [
            models.UniqueConstraint(fields=["entity", "slug"], name="uniq_formcategory_entity_slug"),
            models.UniqueConstraint(fields=["entity", "name"], name="uniq_formcategory_entity_name"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not (self.slug or "").strip():
            from .slug_utils import unique_slug_within

            self.slug = unique_slug_within(
                FormCategory.objects.filter(entity_id=self.entity_id),
                self.name,
                exclude_pk=self.pk,
                max_length=80,
                fallback="category",
            )
        super().save(*args, **kwargs)


class Form(models.Model):
    """A publishable form definition (composed in /manage/, no code)."""

    entity = models.ForeignKey(
        Entity,
        on_delete=models.PROTECT,
        related_name="forms",
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=120, db_index=True)
    description = models.TextField(blank=True)
    submission_deadline = models.DateField(
        "Submission deadline",
        null=True,
        blank=True,
        help_text="If set, respondents cannot submit after this calendar date (end of day in the site time zone).",
    )
    category = models.ForeignKey(
        FormCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="forms",
        help_text="Optional group such as HR or Finance.",
    )
    is_published = models.BooleanField(default=False)
    one_time_submit = models.BooleanField(
        "One response per respondent",
        default=False,
        help_text="When on, each signed-in account may submit at most once. Visitors who are not signed in "
        "are limited to one submit per browser (session) after a successful response.",
    )
    is_for_public = models.BooleanField(
        "Allow access without signing in",
        default=True,
        help_text="When on, anyone with the link can open and submit this form without an account. "
        "When off, only signed-in users can use the form (anonymous visitors are sent to sign in).",
    )

    class LayoutDirection(models.TextChoices):
        AUTO = "auto", _("Follow the site language")
        RTL = "rtl", _("Right to left (Arabic)")
        LTR = "ltr", _("Left to right (English)")

    layout_direction = models.CharField(
        "Default layout direction",
        max_length=4,
        choices=LayoutDirection.choices,
        default=LayoutDirection.AUTO,
        help_text="Text direction of the public form pages. “Follow the site language” switches with the "
        "visitor's language; RTL or LTR pins the layout regardless of language.",
    )
    allow_submission_forward = models.BooleanField(
        "Allow forwarding submissions",
        default=False,
        help_text="When on, staff can record that a submission was forwarded to another user (shown on the timeline).",
    )

    class RoutingMode(models.TextChoices):
        FIXED_STEPS = "fixed_steps", _("Fixed steps (configured order and assignees)")
        DYNAMIC = "dynamic", _("Dynamic routing (choose who receives it next, each time)")

    routing_mode = models.CharField(
        "Workflow routing",
        max_length=20,
        choices=RoutingMode.choices,
        default=RoutingMode.FIXED_STEPS,
        help_text="Fixed steps follow the ordered steps and assignees configured below. Dynamic routing lets "
        "whoever is acting choose the next person by name or job title instead of a pre-built path.",
    )
    submit_route_role = models.CharField(
        "Route new submissions to role",
        max_length=255,
        blank=True,
        help_text="Dynamic routing only. When set, a new submission automatically goes to whoever holds "
        "this job title instead of opening to any organization member. Matched the same loose way as the "
        "“Route to” search (name or job title, partial match). Leave blank to keep today's behaviour.",
    )
    submit_route_suggested_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submit_route_suggestions",
        help_text="Learned automatically: the last person manually routed to for this form's submit-stage "
        "role, used as the default pick when more than one person currently holds that role.",
    )
    print_template = models.FileField(
        "Print template (DOCX or PDF)",
        upload_to="form_print_templates/%Y/%m/",
        max_length=500,
        blank=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["docx", "pdf"],
            )
        ],
        help_text="Optional primary template for merged documents. "
        "DOCX: Jinja placeholders like {{ field_name }} matching each field internal name "
        "(underscores; hyphens map to underscores). "
        "PDF: fillable AcroForm field names match internal slugs. "
        "Also: form_title, submitter_email, reference_token, submitted_at, current_step_label. "
        "Upload a separate ODT below if you want an editable LibreOffice copy for staff.",
    )
    print_template_odt = models.FileField(
        "Print template (ODT, optional)",
        upload_to="form_print_templates/%Y/%m/",
        max_length=500,
        blank=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["odt"],
            )
        ],
        help_text="Optional. ODT copy for download and editing in LibreOffice; answers are not merged into this file. "
        "Use the DOCX or PDF template above for merged outputs with submission data.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_forms",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Set when a super admin archives this form (soft delete). Archived forms are hidden from public and normal workspace lists.",
    )
    public_share_key = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Optional secret segment for public links. When set, the form only opens when the URL includes "
        "?share=<this uuid> (QR codes include it). Regenerate on the Share QR page to invalidate old prints.",
    )
    hide_from_form_lists = models.BooleanField(
        "Hide from portal & home lists",
        default=False,
        help_text="When on, this form is omitted from the organization public portal, the global home directory, "
        "and the workspace home form list (useful for related-only or parent-driven forms). "
        "Direct links, QR codes, submissions, and workspace form pages still work.",
    )
    class IntroVenueType(models.TextChoices):
        IN_PERSON = "in_person", _("In person")
        ONLINE = "online", _("Online")
        HYBRID = "hybrid", _("Hybrid")

    class IntroListStyle(models.TextChoices):
        BULLET = "bullet", _("Bullet points")
        ORDERED = "ordered", _("Numbered list")

    intro_page_enabled = models.BooleanField(
        "Show announcement page before applying",
        default=False,
        help_text="Off by default. When on, applicants see your announcement first, then apply.",
    )
    intro_title = models.CharField(
        "Headline",
        max_length=255,
        blank=True,
        help_text="Optional. Defaults to the form title if blank.",
    )
    intro_subtitle = models.CharField(
        "Tagline",
        max_length=400,
        blank=True,
        help_text="Optional short line under the headline.",
    )
    intro_description = models.TextField(
        "Message",
        blank=True,
        help_text="Optional. Plain text or simple HTML (bold, links, lists).",
    )
    intro_details = models.TextField(
        "Highlights",
        blank=True,
        help_text="Optional. One highlight per line.",
    )
    intro_details_list_style = models.CharField(
        "Highlights list style",
        max_length=16,
        choices=IntroListStyle.choices,
        default=IntroListStyle.BULLET,
        help_text="How highlight lines appear on the announcement page.",
    )
    intro_venue_type = models.CharField(
        "Format",
        max_length=20,
        blank=True,
        choices=IntroVenueType.choices,
        help_text="Optional. In person, online, or hybrid.",
    )
    intro_location = models.CharField(
        "Venue or location",
        max_length=500,
        blank=True,
        help_text="Optional address, room, or online access note.",
    )
    intro_map_url = models.URLField(
        "Map link",
        max_length=500,
        blank=True,
        help_text="Optional link to maps or directions.",
    )
    intro_contact_name = models.CharField(
        "Contact name",
        max_length=200,
        blank=True,
        help_text="Optional organizer or point of contact.",
    )
    intro_contact_email = models.EmailField(
        "Contact email",
        blank=True,
    )
    intro_contact_phone = models.CharField(
        "Contact phone",
        max_length=80,
        blank=True,
    )
    intro_fee = models.CharField(
        "Registration fee",
        max_length=120,
        blank=True,
        help_text='Optional, e.g. "Free" or "25 KWD".',
    )
    intro_capacity = models.PositiveIntegerField(
        "Capacity (seats)",
        null=True,
        blank=True,
        help_text="Optional maximum registrations.",
    )
    intro_show_capacity = models.BooleanField(
        "Show remaining seats on announcement page",
        default=True,
        help_text="When capacity is set, show seats left on the announcement page. "
        "Turn off to hide capacity there while keeping the limit for your own reference.",
    )
    intro_apply_button_label = models.CharField(
        "Apply button label",
        max_length=80,
        blank=True,
        help_text='Optional call-to-action, e.g. "Register now". Defaults to "Apply now".',
    )
    intro_video_url = models.URLField(
        "Featured video URL",
        max_length=500,
        blank=True,
        help_text="Optional YouTube or Vimeo link (embedded when supported).",
    )
    intro_attachment = models.FileField(
        "Brochure (PDF)",
        upload_to="form_intro_attachments/%Y/%m/",
        max_length=500,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf"]),
        ],
        help_text="Optional PDF download (brochure, instructions, etc.).",
    )
    intro_event_start = models.DateTimeField(
        "Starts",
        null=True,
        blank=True,
        help_text="Optional schedule start.",
    )
    intro_event_end = models.DateTimeField(
        "Ends",
        null=True,
        blank=True,
        help_text="Optional schedule end.",
    )
    intro_rules = models.TextField(
        "Guidelines",
        blank=True,
        help_text="Optional. One guideline per line.",
    )
    intro_rules_list_style = models.CharField(
        "Guidelines list style",
        max_length=16,
        choices=IntroListStyle.choices,
        default=IntroListStyle.BULLET,
        help_text="How guideline lines appear on the announcement page.",
    )

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["entity", "slug"], name="uniq_form_entity_slug"),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.entity_id and not (self.slug or "").strip():
            from .slug_utils import unique_form_slug

            self.slug = unique_form_slug(self.title, self.entity, exclude_pk=self.pk)
        super().save(*args, **kwargs)

    @property
    def is_starter_sample_form(self) -> bool:
        from .sample_forms_library import is_starter_sample_slug

        return is_starter_sample_slug(self.slug)

    @property
    def is_unclaimed_starter_sample(self) -> bool:
        from .sample_forms_library import is_unclaimed_starter_sample

        return is_unclaimed_starter_sample(self)

    def build_public_form_absolute_url(self, request) -> str:
        """Absolute URL to the public entry (information page or form), including ``?share=`` when set."""
        from .subdomain import portal_absolute_uri

        query = {"share": str(self.public_share_key)} if self.public_share_key else None
        return portal_absolute_uri(
            request,
            "magicforms:form_public",
            entity=self.entity,
            slug=self.slug,
            query=query,
        )

    def build_public_apply_url(self, request) -> str:
        """URL that opens the submission form (skips the information page when enabled)."""
        from .subdomain import portal_absolute_uri

        query = {"apply": "1"}
        if self.public_share_key:
            query["share"] = str(self.public_share_key)
        return portal_absolute_uri(
            request,
            "magicforms:form_public",
            entity=self.entity,
            slug=self.slug,
            query=query,
        )

    def build_related_apply_url(self, request, access_token) -> str:
        """Related (child) form URL that skips the information page when enabled."""
        from .subdomain import portal_absolute_uri

        return portal_absolute_uri(
            request,
            "magicforms:related_form_public",
            entity=self.entity,
            slug=self.slug,
            access_token=access_token,
            query={"apply": "1"},
        )

    def intro_details_lines(self) -> list[str]:
        return [ln.strip() for ln in (self.intro_details or "").splitlines() if ln.strip()]

    def intro_rules_lines(self) -> list[str]:
        return [ln.strip() for ln in (self.intro_rules or "").splitlines() if ln.strip()]

    def intro_details_use_ordered_list(self) -> bool:
        return self.intro_details_list_style == self.IntroListStyle.ORDERED

    def intro_rules_use_ordered_list(self) -> bool:
        return self.intro_rules_list_style == self.IntroListStyle.ORDERED

    def get_ordered_intro_slides(self):
        return self.intro_slides.order_by("sort_order", "id")

    def intro_apply_label(self) -> str:
        custom = (self.intro_apply_button_label or "").strip()
        return custom or _("Apply now")

    def intro_seats_remaining(self) -> int | None:
        if not self.intro_capacity:
            return None
        used = self.submissions.count()
        return max(0, int(self.intro_capacity) - used)

    def intro_show_capacity_on_page(self) -> bool:
        return bool(self.intro_capacity) and self.intro_show_capacity

    def submission_deadline_has_passed(self) -> bool:
        if not self.submission_deadline:
            return False
        return timezone.localdate() > self.submission_deadline

    def get_ordered_fields(self):
        return self.fields.order_by("order", "id").select_related(
            "visibility_control_field",
            "section",
        )

    def public_dir(self) -> str:
        """``"rtl"`` / ``"ltr"`` for the public pages of this form (falls back to the active language)."""
        from django.utils.translation import get_language_bidi

        if self.layout_direction in (self.LayoutDirection.RTL, self.LayoutDirection.LTR):
            return self.layout_direction
        return "rtl" if get_language_bidi() else "ltr"

    def get_ordered_workflow_steps(self):
        return self.workflow_steps.order_by("order", "id").prefetch_related("assigned_users")

    @property
    def uses_dynamic_routing(self) -> bool:
        return self.routing_mode == self.RoutingMode.DYNAMIC

    def initial_workflow_step(self):
        return self.workflow_steps.order_by("order", "id").first()

    def next_workflow_step_after(self, step):
        """Next step after ``step`` in order by ``order``, then ``id``. None if last or unknown."""
        if step is None:
            return None
        ordered = list(self.workflow_steps.order_by("order", "id"))
        for i, s in enumerate(ordered):
            if s.pk == step.pk:
                return ordered[i + 1] if i + 1 < len(ordered) else None
        return None

    def previous_workflow_step_before(self, step):
        """Step before ``step`` in order by ``order``, then ``id``. None if first or unknown."""
        if step is None:
            return None
        ordered = list(self.workflow_steps.order_by("order", "id"))
        for i, s in enumerate(ordered):
            if s.pk == step.pk:
                return ordered[i - 1] if i > 0 else None
        return None

    def get_ordered_sections(self):
        return self.sections.order_by("order", "id")

    def next_free_logo_header_slot(self) -> int:
        """First open header position for a new logo (left, then center, then right)."""
        used = set(self.logos.values_list("header_slot", flat=True))
        for slot in FormLogo.HeaderSlot:
            if slot.value not in used:
                return slot.value
        return FormLogo.HeaderSlot.LEFT.value


def form_intro_slide_upload_to(instance, filename):
    safe = get_valid_filename(filename) if filename else "slide.bin"
    return f"form_intro_slides/{instance.form_id}/{safe}"


class FormIntroSlide(models.Model):
    """Optional images shown as a slideshow on the form information page."""

    MAX_PER_FORM = 15

    form = models.ForeignKey(
        Form,
        on_delete=models.CASCADE,
        related_name="intro_slides",
    )
    image = models.ImageField(
        _("Gallery image"),
        upload_to=form_intro_slide_upload_to,
        max_length=500,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["png", "jpg", "jpeg", "gif", "webp"],
            )
        ],
        help_text=_(
            "Recommended 1920×1080 px (16:9 widescreen). The slideshow is wide; "
            "other aspect ratios are centered and may be cropped."
        ),
    )
    caption = models.CharField(
        _("Caption"),
        max_length=255,
        blank=True,
        help_text=_("Optional text shown under the image in the slideshow."),
    )
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = _("Announcement gallery image")
        verbose_name_plural = _("Announcement gallery images")

    def __str__(self):
        return f"Intro slide ({self.form_id})"


def form_logo_upload_to(instance, filename):
    safe = get_valid_filename(filename) if filename else "logo.bin"
    return f"form_logos/{instance.form_id}/{safe}"


class FormLogo(models.Model):
    """Up to three brand marks shown on the public form (managed in /manage/)."""

    MAX_PER_FORM = 3

    class HeaderSlot(models.IntegerChoices):
        LEFT = 0, _("Left (beside title column)")
        CENTER = 1, _("Center (above title)")
        RIGHT = 2, _("Right (beside title column)")

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="logos")
    image = models.FileField(
        "Logo file",
        upload_to=form_logo_upload_to,
        max_length=500,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "svg"],
            )
        ],
    )
    header_slot = models.PositiveSmallIntegerField(
        _("Position in header"),
        choices=HeaderSlot.choices,
        default=HeaderSlot.LEFT,
        help_text=_("Where this image appears in the live form header."),
    )
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["header_slot", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["form", "header_slot"],
                name="magicforms_formlogo_form_header_slot_uniq",
            ),
        ]

    def __str__(self):
        return f"Logo ({self.form_id})"

    def save(self, *args, **kwargs):
        self.sort_order = int(self.header_slot)
        if (
            self.image
            and hasattr(self.image, "_committed")
            and not self.image._committed
        ):
            from .logo_processing import maybe_replace_image_field_with_knockout_png

            maybe_replace_image_field_with_knockout_png(self.image)
        super().save(*args, **kwargs)


class FormSection(models.Model):
    """Collapsible grouping on the public form; fields can belong to one section."""

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="sections")
    order = models.PositiveIntegerField(default=0, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    starts_collapsed = models.BooleanField(
        "Starts collapsed",
        default=False,
        help_text="When on, the section is closed until the respondent taps to expand it.",
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class FieldType(models.TextChoices):
    TEXT = "text", "Short text"
    TEXTAREA = "textarea", "Paragraph"
    EMAIL = "email", "Email"
    NUMBER = "number", "Number"
    DATE = "date", "Date"
    SELECT = "select", "Dropdown"
    RADIO = "radio", "Radio buttons"
    CHECKBOX = "checkbox", "Checkbox"
    CHECKLIST = "checklist", "Checklist"
    FILE = "file", "File upload"
    HINT = "hint", "Hint (information only)"
    LABEL = "label", "Label (display text only)"
    BREAK = "break", "Break (line spacer)"


DISPLAY_ONLY_FIELD_TYPES = frozenset({FieldType.HINT, FieldType.LABEL, FieldType.BREAK})


class OptionsLayout(models.TextChoices):
    HORIZONTAL = "horizontal", "Horizontal"
    VERTICAL = "vertical", "Vertical"


def submission_value_attachment_upload_to(instance, filename):
    base = get_valid_filename(filename) if filename else "upload.bin"
    return f"submissions/{instance.submission_id}/f{instance.field_id}_{base}"


class FormField(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="fields")
    order = models.PositiveIntegerField(default=0, db_index=True)
    field_type = models.CharField(max_length=32, choices=FieldType.choices, default=FieldType.TEXT)
    name = models.SlugField(max_length=80, help_text="Internal key (letters, numbers, hyphens).")
    mapping_key = models.CharField(
        "Mapping name",
        max_length=80,
        blank=True,
        help_text="Optional: User or profile attribute to pre-fill for signed-in users (e.g. email, "
        "first_name, job_title, civil_id, employee_number, department, age). Matches User fields, "
        "then user.profile (EmployeeProfile) if it exists.",
    )
    label = models.CharField(max_length=255)
    hint = models.TextField(
        blank=True,
        help_text="Optional guidance on the live form (under the label). Not stored as an answer.",
    )
    help_text = models.CharField(max_length=500, blank=True)
    placeholder = models.CharField(max_length=255, blank=True)
    required = models.BooleanField(default=False)
    choices_text = models.TextField(
        blank=True,
        help_text="For dropdown, radio, or checklist: one option per line.",
    )
    options_layout = models.CharField(
        "Display options",
        max_length=20,
        choices=OptionsLayout.choices,
        default=OptionsLayout.VERTICAL,
        help_text="For radio buttons and checklist: show choices in a row or a column.",
    )
    inline = models.BooleanField(
        "Inline row",
        default=False,
        help_text="Show on the same row as neighboring fields that are also set to inline.",
    )
    visibility_control_field = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="visibility_dependent_fields",
        help_text="Optional: another field whose value controls whether this field is shown.",
    )
    visibility_show_when_values = models.TextField(
        blank=True,
        help_text="When the control field matches any line below (one per line), this field is visible. "
        "For a single checkbox use yes; for a checklist use one line per option label (matches if any "
        "checked option equals a line). You can also match the exact combination by listing all selected "
        "labels as one line separated by newlines.",
    )
    section = models.ForeignKey(
        FormSection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fields",
        help_text="Optional: place this field inside a collapsible section.",
    )
    validation_min_length = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Minimum character count (after trimming). Applies to short text, paragraph, email, dropdown, radio.",
    )
    validation_max_length = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Maximum character count. Also bounds the HTML input limit for short text / paragraph.",
    )
    validation_must_contain = models.CharField(
        max_length=500,
        blank=True,
        help_text='Substring that must appear (case-insensitive), e.g. "@" or a code word.',
    )
    validation_must_not_contain = models.CharField(
        max_length=500,
        blank=True,
        help_text="Substring that must not appear (case-insensitive).",
    )
    validation_must_equal = models.CharField(
        max_length=500,
        blank=True,
        help_text="If set, the submitted value must match this text exactly (after trimming).",
    )
    validation_regex = models.CharField(
        max_length=500,
        blank=True,
        help_text='Optional regex checked against the value (Python re syntax), e.g. ^[A-Z]{3}-\\d{4}$.',
    )
    validation_integer_only = models.BooleanField(
        default=False,
        help_text="When on, numeric fields must not use decimals.",
    )
    validation_decimal_min = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Numeric fields: smallest allowed number (inclusive).",
    )
    validation_decimal_max = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Numeric fields: largest allowed number (inclusive).",
    )
    validation_date_after = models.DateField(
        null=True,
        blank=True,
        help_text="Date fields must be on or after this calendar day.",
    )
    validation_date_before = models.DateField(
        null=True,
        blank=True,
        help_text="Date fields must be on or before this calendar day.",
    )
    validation_unique_value = models.BooleanField(
        default=False,
        help_text="When on, reject a new submission if this field’s answer was already submitted "
        "on this form (e.g. national ID or email). Not for file uploads or checklist fields.",
    )

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["form", "name"], name="uniq_form_field_name"),
        ]

    def __str__(self):
        return f"{self.label} ({self.name})"

    def save(self, *args, **kwargs):
        if self.form_id and not (self.name or "").strip():
            from .slug_utils import unique_form_field_name

            base = (self.label or "").strip() or "field"
            self.name = unique_form_field_name(base, self.form, exclude_pk=self.pk)
        super().save(*args, **kwargs)

    def choice_list(self):
        if not self.choices_text.strip():
            return []
        return [line.strip() for line in self.choices_text.splitlines() if line.strip()]

    def visibility_trigger_values(self):
        if not self.visibility_show_when_values.strip():
            return []
        return [line.strip() for line in self.visibility_show_when_values.splitlines() if line.strip()]


class WorkflowStep(models.Model):
    """Ordered stages a submission moves through (defined per form in admin)."""

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="workflow_steps")
    order = models.PositiveIntegerField(default=0, db_index=True)
    slug = models.SlugField(max_length=80)
    label = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    assigned_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="assigned_workflow_steps",
        verbose_name="Assignees",
        help_text="Organization members who receive or handle submissions while they are on this step.",
    )

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["form", "slug"], name="uniq_workflow_step_slug"),
        ]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        if self.form_id and not (self.slug or "").strip():
            from .slug_utils import unique_workflow_step_slug

            self.slug = unique_workflow_step_slug(self.label, self.form, exclude_pk=self.pk)
        super().save(*args, **kwargs)


class SupplementaryFormLink(models.Model):
    """
    Child form tied to a parent form: when a base submission reaches ``trigger_step``,
    a SupplementarySubmission row is created so the applicant can open the child form via token URL.
    """

    parent_form = models.ForeignKey(
        "Form",
        on_delete=models.CASCADE,
        related_name="related_links_out",
    )
    child_form = models.ForeignKey(
        "Form",
        on_delete=models.CASCADE,
        related_name="related_links_in",
    )
    trigger_step = models.ForeignKey(
        WorkflowStep,
        on_delete=models.CASCADE,
        related_name="related_link_triggers",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parent_form", "child_form", "trigger_step"],
                name="uniq_supplementary_parent_child_trigger",
            ),
        ]

    def __str__(self):
        return f"{self.parent_form_id} → {self.child_form_id} @ {self.trigger_step_id}"

    def clean(self):
        from django.core.exceptions import ValidationError

        errs = {}
        if self.trigger_step_id and self.parent_form_id:
            if self.trigger_step.form_id != self.parent_form_id:
                errs["trigger_step"] = "The workflow step must belong to the parent form."
        if self.child_form_id and self.parent_form_id:
            if self.child_form.entity_id != self.parent_form.entity_id:
                errs["child_form"] = "The child form must belong to the same organization as the parent."
            elif self.child_form_id == self.parent_form_id:
                errs["child_form"] = "Choose a different form than the parent."
        if errs:
            raise ValidationError(errs)


class SupplementarySubmission(models.Model):
    """One invitation for the applicant to submit ``link.child_form`` for a given parent submission."""

    link = models.ForeignKey(
        SupplementaryFormLink,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    parent_submission = models.ForeignKey(
        "FormSubmission",
        on_delete=models.CASCADE,
        related_name="related_invitations",
    )
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    child_submission = models.OneToOneField(
        "FormSubmission",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="related_invitation_slot",
    )
    invited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["link", "parent_submission"],
                name="uniq_supplementary_invite_per_parent_submission",
            ),
        ]

    def __str__(self):
        return f"rel {self.parent_submission_id} → {self.link.child_form_id}"


class WorkflowDelegation(models.Model):
    """
    Staff delegation: ``delegate`` may take workflow actions (inbox, approve/reject) for steps
    assigned to ``delegator`` while the delegation is active and within its date range.
    Scoped to one entity so delegates only cover work inside that organization.
    """

    entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="workflow_delegations",
    )
    delegator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workflow_delegations_given",
        help_text="Assignee who is covered (out of office, etc.).",
    )
    delegate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workflow_delegations_received",
        help_text="Staff user who may act on their behalf.",
    )
    valid_from = models.DateField(
        blank=True,
        null=True,
        help_text="Optional. First calendar day this delegation applies; blank = immediately.",
    )
    valid_until = models.DateField(
        blank=True,
        null=True,
        help_text="Optional. Last calendar day this delegation applies; blank = no end date.",
    )
    notes = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    directory_api_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="ID from the directory login API delegations list, when synced automatically.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workflow_delegations_created",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "directory_api_id"],
                condition=models.Q(directory_api_id__isnull=False),
                name="magicforms_workflowdelegation_entity_directory_api_id_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.delegator_id} → {self.delegate_id}"


class FormSubmission(models.Model):
    """One filled-in form from an end user."""

    class WorkflowState(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="submissions")
    reference_token = models.CharField(max_length=20, unique=True, editable=False)
    track_code = models.CharField(
        max_length=5,
        blank=True,
        editable=False,
        db_index=True,
        help_text="Short 5-digit code; with the respondent's email it opens the public track page.",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitter_email = models.EmailField(
        blank=True,
        help_text="When the respondent was signed in, their account email is copied here on submit; "
        "otherwise this stays blank (anonymous in the database).",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="form_submissions",
        help_text="Set when the respondent was signed in at submit time (used for one-response enforcement).",
    )
    current_step = models.ForeignKey(
        WorkflowStep,
        on_delete=models.PROTECT,
        related_name="submissions_here",
        null=True,
        blank=True,
    )
    current_holder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="held_submissions",
        help_text="Dynamic routing only: who currently has this submission for action. "
        "Fixed-step forms use current_step and assigned_users instead.",
    )
    current_stage_label = models.CharField(
        "Current stage",
        max_length=255,
        blank=True,
        help_text="Dynamic routing only: free-text stage shown on the timeline and inbox, chosen at the last handoff.",
    )
    workflow_state = models.CharField(
        max_length=20,
        choices=WorkflowState.choices,
        default=WorkflowState.IN_PROGRESS,
        db_index=True,
        help_text="Staff approve/reject drives progression; completed or rejected stops the inbox queue.",
    )

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        ref = str(self.reference_token)
        return f"{self.form.title} · {ref[:8]}…"

    def get_print_current_step_label(self) -> str:
        """Label for merged documents and public status when step is cleared."""
        if self.workflow_state == self.WorkflowState.COMPLETED:
            return "Completed"
        if self.workflow_state == self.WorkflowState.REJECTED:
            return "Rejected"
        if self.current_step_id and self.current_step:
            return self.current_step.label
        return ""

    @staticmethod
    def generate_track_code() -> str:
        import secrets

        return f"{secrets.randbelow(100000):05d}"

    def save(self, *args, **kwargs):
        from django.db import IntegrityError

        from .submission_reference import generate_submission_reference_token

        if not self.track_code:
            self.track_code = self.generate_track_code()
        if self.reference_token:
            super().save(*args, **kwargs)
            return
        attempts = 0
        while attempts < 32:
            self.reference_token = generate_submission_reference_token(self.__class__)
            try:
                super().save(*args, **kwargs)
                return
            except IntegrityError:
                attempts += 1
                self.reference_token = ""
        raise RuntimeError("Could not save FormSubmission with a unique reference_token")



class FormSubmissionDraft(models.Model):
    """
    Saved progress on a public form (not yet submitted). The resume token is the
    credential for guests; signed-in users also see their drafts on the drafts page.
    Stores raw posted values keyed by ``f_<field_pk>``; file uploads are not kept.
    """

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="drafts")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="form_drafts",
    )
    resume_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"draft form={self.form_id} user={self.user_id or 'guest'} token={str(self.resume_token)[:8]}…"


class StaffInboxSubmissionDetailView(models.Model):
    """Staff user opened this submission in manage detail (inbox star is muted after first visit)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="inbox_submission_detail_views",
    )
    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="inbox_detail_views",
    )
    seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "submission"],
                name="uniq_staff_inbox_detail_view_user_submission",
            ),
        ]

    def __str__(self):
        return f"user={self.user_id} submission={self.submission_id}"


class SubmissionValue(models.Model):
    submission = models.ForeignKey(FormSubmission, on_delete=models.CASCADE, related_name="values")
    field = models.ForeignKey(FormField, on_delete=models.CASCADE, related_name="submission_values")
    value = models.TextField(blank=True)
    attachment = models.FileField(
        "Uploaded file",
        upload_to=submission_value_attachment_upload_to,
        max_length=500,
        blank=True,
        help_text="Populated when the form field type is file upload.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["submission", "field"], name="uniq_submission_field_value"),
        ]

    def __str__(self):
        return f"{self.field.name}={self.value[:40]}"


class SubmissionEvent(models.Model):
    """Timeline for follow-up: submissions, step changes, notes."""

    class Kind(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        STEP_CHANGED = "step_changed", "Workflow step changed"
        NOTE = "note", "Note"
        STEP_APPROVED = "step_approved", "Step approved"
        WORKFLOW_COMPLETED = "workflow_completed", "Workflow completed"
        APPROVE_UNDONE = "approve_undone", "Approval undone"
        WORKFLOW_REJECTED = "workflow_rejected", "Workflow rejected"
        ROUTED = "routed", "Routed to a person"
        ATTACHMENT_ADDED = "attachment_added", "Document attached"
        FORWARDED = "forwarded", "Forwarded"
        SUPPLEMENTARY_INVITED = "supplementary_invited", "Related form available"
        SUPPLEMENTARY_SUBMITTED = "supplementary_submitted", "Related form submitted"

    submission = models.ForeignKey(FormSubmission, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    step = models.ForeignKey(
        WorkflowStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submission_events",
    )
    message = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submission_events",
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} @ {self.created_at}"


def submission_user_document_upload_to(instance, filename):
    safe = get_valid_filename(filename) if filename else "document.bin"
    return f"submission_user_documents/{instance.submission_id}/{uuid.uuid4().hex[:10]}_{safe}"


class SubmissionAttachment(models.Model):
    """Extra documents uploaded by the respondent (track page) or staff (manage) for a submission."""

    MAX_PER_SUBMISSION = 40
    MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB

    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="document_attachments",
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional label shown next to the download link.",
    )
    file = models.FileField(
        "Document",
        upload_to=submission_user_document_upload_to,
        max_length=500,
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "pdf",
                    "doc",
                    "docx",
                    "png",
                    "jpg",
                    "jpeg",
                    "gif",
                    "webp",
                    "txt",
                    "csv",
                    "xlsx",
                    "xls",
                    "odt",
                ],
            )
        ],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submission_attachments_uploaded",
        help_text="Staff user when uploaded from manage; empty when uploaded from the public track page.",
    )

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Attachment {self.pk} · submission {self.submission_id}"


class SubmissionThreadMessage(models.Model):
    """Discussion thread on a submission (studio manage detail); visible to everyone who can open that page."""

    MAX_BODY_LEN = 4000

    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="thread_messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submission_thread_messages",
    )
    body = models.TextField(max_length=MAX_BODY_LEN)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Thread #{self.pk} · submission {self.submission_id}"


class SubmissionApplicantMessage(models.Model):
    """
    Chat between studio staff and the applicant on a submission.
    Staff write from the manage detail page; the applicant reads and replies on the
    public track page (no account needed — the capability URL or track code is the credential).
    """

    MAX_BODY_LEN = 4000

    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="applicant_messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applicant_chat_messages",
        help_text="Staff author; empty for applicant replies from the public track page.",
    )
    is_from_applicant = models.BooleanField(default=False, db_index=True)
    body = models.TextField(max_length=MAX_BODY_LEN)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        who = "applicant" if self.is_from_applicant else f"user={self.author_id}"
        return f"applicant-chat #{self.pk} ({who}) submission={self.submission_id}"


class SubmissionThreadLastRead(models.Model):
    """Per-user last-seen thread message id on a submission (for inbox unread indicator)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submission_thread_last_reads",
    )
    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="thread_last_reads",
    )
    last_seen_message_id = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "submission"],
                name="uniq_submission_thread_last_read_user_submission",
            ),
        ]

    def __str__(self):
        return f"thread read user={self.user_id} submission={self.submission_id}"


class SubmissionPrivateStickyNote(models.Model):
    """Per-user private reminder on a submission (manage detail only); not visible to other users."""

    MAX_BODY_LEN = 8000

    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="private_sticky_notes",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submission_private_sticky_notes",
    )
    body = models.TextField(max_length=MAX_BODY_LEN, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "user"],
                name="uniq_submission_private_sticky_note_user",
            ),
        ]

    def __str__(self):
        return f"Private note user={self.user_id} submission={self.submission_id}"


class UserSubmissionTask(models.Model):
    """Per-user to-do item pointing at a submission (inbox / search / detail)."""

    MAX_NOTE_LEN = 500

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submission_tasks",
    )
    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="user_tasks",
    )
    note = models.CharField(max_length=MAX_NOTE_LEN, blank=True)
    due_date = models.DateField(
        "Deadline",
        null=True,
        blank=True,
        db_index=True,
        help_text="Optional follow-up date for this task.",
    )
    is_done = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "submission"],
                name="uniq_mf_user_submission_task_user_sub",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_done", "-created_at"]),
        ]

    def __str__(self):
        return f"task user={self.user_id} sub={self.submission_id} done={self.is_done}"


class ResponsesGridView(models.Model):
    """Saved column layout for the studio responses grid (per form, per owner)."""

    MAX_NAME_LEN = 120

    form = models.ForeignKey(
        Form,
        on_delete=models.CASCADE,
        related_name="responses_grid_views",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="responses_grid_views_owned",
    )
    name = models.CharField(max_length=MAX_NAME_LEN)
    column_keys = models.JSONField(default=list, blank=True)
    is_default = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "form", "name"],
                name="uniq_mf_responses_grid_view_owner_form_name",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.form_id})"


class ResponsesGridViewShare(models.Model):
    """Share a saved grid view with another staff user."""

    view = models.ForeignKey(
        ResponsesGridView,
        on_delete=models.CASCADE,
        related_name="shares",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="responses_grid_views_shared",
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="responses_grid_views_shared_out",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["view", "user"],
                name="uniq_mf_responses_grid_view_share_view_user",
            ),
        ]

    def __str__(self):
        return f"view={self.view_id} → user={self.user_id}"


class SubmissionTimelineShare(models.Model):
    """Grant a user read access to the full-page submission timeline."""

    MAX_SHARE_MESSAGE_LEN = 500

    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="timeline_shares",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submission_timelines_shared",
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submission_timelines_shared_out",
    )
    share_message = models.CharField(max_length=MAX_SHARE_MESSAGE_LEN, blank=True)
    first_viewed_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When set, the recipient hid this share on Home; access via share is revoked.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "user"],
                name="uniq_mf_submission_timeline_share_sub_user",
            ),
        ]

    def __str__(self):
        return f"timeline sub={self.submission_id} → user={self.user_id}"


class SubmissionUserTag(models.Model):
    """Per-user private labels on a submission (studio manage detail and search)."""

    MAX_LABEL_LEN = 64
    MAX_TAGS_PER_SUBMISSION = 50

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submission_user_tags",
    )
    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="user_tags",
    )
    label = models.CharField(max_length=MAX_LABEL_LEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["label"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "submission", "label"],
                name="uniq_mf_submission_user_tag_user_sub_label",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "label"]),
        ]

    def __str__(self):
        return f"tag {self.label!r} user={self.user_id} sub={self.submission_id}"

    @classmethod
    def normalize_label(cls, raw: str) -> str:
        s = (raw or "").strip().lower()
        s = re.sub(r"\s+", " ", s)
        return s[: cls.MAX_LABEL_LEN]

    @classmethod
    def parse_tag_input(cls, blob: str) -> list[str]:
        parts = re.split(r"[\n,;]+", blob or "")
        seen: set[str] = set()
        out: list[str] = []
        for p in parts:
            n = cls.normalize_label(p)
            if not n or n in seen:
                continue
            seen.add(n)
            out.append(n)
            if len(out) >= cls.MAX_TAGS_PER_SUBMISSION:
                break
        return out


class SubmissionUserHighlight(models.Model):
    """Per-user row highlight color on a submission (personal cue in the workspace inbox)."""

    COLOR_CHOICES = [
        ("yellow", _("Yellow")),
        ("green", _("Green")),
        ("blue", _("Blue")),
        ("red", _("Red")),
        ("purple", _("Purple")),
        ("orange", _("Orange")),
        ("gray", _("Gray")),
    ]
    COLOR_KEYS = frozenset(c[0] for c in COLOR_CHOICES)
    # Palette offered on the responses grid picker.
    RESPONSES_GRID_COLOR_KEYS = ("red", "green", "orange", "gray")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submission_highlights",
    )
    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="user_highlights",
    )
    color = models.CharField(max_length=16, choices=COLOR_CHOICES)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "submission"],
                name="uniq_mf_submission_user_highlight",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "color"]),
        ]

    def __str__(self):
        return f"highlight {self.color} user={self.user_id} sub={self.submission_id}"


class EmployeeProfile(models.Model):
    """
    Extended HR-style fields for staff users; linked as ``user.profile`` for form field mapping.
    """

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full-time"
        PART_TIME = "part_time", "Part-time"
        CONTRACT = "contract", "Contract"
        INTERN = "intern", "Intern"
        OTHER = "other", "Other"

    class Gender(models.TextChoices):
        UNSPECIFIED = "", "— Prefer not to say —"
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        NON_BINARY = "non_binary", "Non-binary"
        OTHER = "other", "Other"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="profile",
    )
    employee_number = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Internal employee or payroll ID.",
    )
    civil_id = models.CharField(
        "Civil / national ID",
        max_length=80,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
    )
    job_title = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    birth_date = models.DateField(blank=True, null=True)
    hire_date = models.DateField(blank=True, null=True)
    degree = models.CharField(
        "Highest degree",
        max_length=200,
        blank=True,
        help_text="e.g. Bachelor of Science, MBA.",
    )
    field_of_study = models.CharField(max_length=200, blank=True)
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True, default="")
    nationality = models.CharField(max_length=120, blank=True)
    work_phone = models.CharField(max_length=40, blank=True)
    mobile_phone = models.CharField("Personal mobile", max_length=40, blank=True)
    work_email = models.EmailField(
        blank=True,
        help_text="Optional; defaults to account email if empty for directory display.",
    )
    office_location = models.CharField(max_length=255, blank=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="team_member_profiles",
        help_text="Direct manager (directory / org chart).",
    )
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True, help_text="Internal HR notes — not shown on public forms.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Employee profile"
        verbose_name_plural = "Employee profiles"

    def __str__(self):
        return f"Profile · {self.user_id}"

    @property
    def age(self) -> int | None:
        """Age in full years from ``birth_date`` (for display and form mapping)."""
        if not self.birth_date:
            return None
        today = timezone.now().date()
        y = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            y -= 1
        return y


def submission_signature_placement_upload_to(instance, filename):
    safe = get_valid_filename(filename) if filename else "signature.png"
    return f"submission_signatures/{instance.submission_id}/{uuid.uuid4().hex[:10]}_{safe}"


class SubmissionSignaturePlacement(models.Model):
    """
    A hand-drawn signature stamped onto the merged PDF of one submission.

    ``page_index`` is zero-based. ``x`` / ``y`` are the centre of the signature as fractions of the
    *displayed* page (origin top-left, as rendered by pdf.js); ``width`` is a fraction of the displayed
    page width. Stamping happens at render time (see ``pdf_signatures.stamp_signature_placements``).
    """

    submission = models.ForeignKey(
        "FormSubmission", on_delete=models.CASCADE, related_name="signature_placements"
    )
    page_index = models.PositiveIntegerField(default=0)
    x = models.FloatField()
    y = models.FloatField()
    width = models.FloatField(default=0.22)
    image = models.FileField(upload_to=submission_signature_placement_upload_to, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submission_signature_placements",
    )

    class Meta:
        ordering = ["page_index", "created_at", "id"]

    def __str__(self):
        return f"signature p{self.page_index + 1} @ ({self.x:.2f}, {self.y:.2f}) for {self.submission_id}"

    def image_bytes(self) -> bytes:
        with self.image.open("rb") as fh:
            return fh.read()


def user_signature_upload_to(instance, filename):
    safe = get_valid_filename(filename) if filename else "signature.png"
    return f"user_signatures/{instance.user_id}/{uuid.uuid4().hex[:10]}_{safe}"


# Used by studio user edit and self-service account signatures page.
USER_SIGNATURE_MAX_PER_USER = 200


class UserSignature(models.Model):
    """Multiple signature images per user (e.g. English / Arabic, wet ink scan)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signatures",
    )
    label = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional label, e.g. Primary, Arabic, or Contract copy.",
    )
    image = models.FileField(
        "Signature image",
        upload_to=user_signature_upload_to,
        max_length=500,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "svg"],
            )
        ],
    )
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    directory_api_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="ID from the directory login API signatures list, when synced automatically.",
    )
    directory_content_sha256 = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 of last imported directory signature bytes; skips re-upload when unchanged.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "directory_api_id"],
                condition=models.Q(directory_api_id__isnull=False),
                name="magicforms_usersignature_user_directory_api_id_uniq",
            ),
        ]

    @classmethod
    def assign_primary(cls, user, signature_pk) -> bool:
        """Put the given signature first (``sort_order`` 0) so merges use it as ``signature_primary``."""
        try:
            pk = int(signature_pk)
        except (TypeError, ValueError):
            return False
        with transaction.atomic():
            sigs = list(cls.objects.filter(user=user).order_by("sort_order", "id"))
            chosen = next((s for s in sigs if s.pk == pk), None)
            if chosen is None:
                return False
            rest = [s for s in sigs if s.pk != pk]
            ordered = [chosen] + rest
            for i, s in enumerate(ordered):
                s.sort_order = i
            cls.objects.bulk_update(ordered, ["sort_order"])
        return True

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        image_included = update_fields is None or "image" in update_fields
        if (
            image_included
            and self.image
            and hasattr(self.image, "_committed")
            and not self.image._committed
        ):
            from .logo_processing import maybe_replace_image_field_with_knockout_png

            maybe_replace_image_field_with_knockout_png(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Signature ({self.user_id}) {self.label or self.pk}"


class FormOutboundConfig(models.Model):
    """One optional outbound POST integration per form (field mapping + auth)."""

    class AuthType(models.TextChoices):
        NONE = "none", "None"
        BEARER = "bearer", "Bearer token"
        HEADER = "header", "Custom header"
        BASIC = "basic", "Basic (secret is base64 user:pass or token)"
        HMAC_SHA256 = "hmac_sha256", "HMAC-SHA256 (secret + timestamp)"

    form = models.OneToOneField(
        Form,
        on_delete=models.CASCADE,
        related_name="outbound_config",
    )
    is_active = models.BooleanField(default=False)
    endpoint_url = models.URLField(max_length=500, blank=True)
    timeout_seconds = models.PositiveSmallIntegerField(default=20)
    auth_type = models.CharField(
        max_length=32,
        choices=AuthType.choices,
        default=AuthType.BEARER,
    )
    auth_header_name = models.CharField(
        max_length=64,
        blank=True,
        default="Authorization",
        help_text="Header for Bearer/custom auth (default Authorization).",
    )
    secret_encrypted = models.TextField(blank=True)
    hmac_header_name = models.CharField(
        max_length=64,
        blank=True,
        default="X-Signature",
    )
    trigger_submitted = models.BooleanField(_("On form submit"), default=True)
    trigger_step_approved = models.BooleanField(_("On step approved"), default=False)
    trigger_workflow_completed = models.BooleanField(_("On workflow completed"), default=True)
    trigger_workflow_rejected = models.BooleanField(_("On workflow rejected"), default=True)
    payload_root_key = models.CharField(
        max_length=64,
        blank=True,
        help_text='Optional JSON wrapper key, e.g. "data".',
    )
    custom_headers_json = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Outbound · {self.form_id}"

    def has_secret(self) -> bool:
        return bool((self.secret_encrypted or "").strip())


class FormSubmitValidationConfig(models.Model):
    """Optional pre-submit POST validation API (HTTP 200 required to accept)."""

    class FailureAction(models.TextChoices):
        BLOCK = "block", "Block submit when the API does not return HTTP 200"
        ALLOW_CONTINUE = (
            "allow_continue",
            "Let the respondent choose to submit anyway",
        )

    form = models.OneToOneField(
        Form,
        on_delete=models.CASCADE,
        related_name="submit_validation_config",
    )
    is_active = models.BooleanField(default=False)
    endpoint_url = models.URLField(max_length=500, blank=True)
    timeout_seconds = models.PositiveSmallIntegerField(default=15)
    auth_type = models.CharField(
        max_length=32,
        choices=FormOutboundConfig.AuthType.choices,
        default=FormOutboundConfig.AuthType.BEARER,
    )
    auth_header_name = models.CharField(
        max_length=64,
        blank=True,
        default="Authorization",
        help_text="Header for Bearer/custom auth (default Authorization).",
    )
    secret_encrypted = models.TextField(blank=True)
    hmac_header_name = models.CharField(
        max_length=64,
        blank=True,
        default="X-Signature",
    )
    payload_root_key = models.CharField(
        max_length=64,
        blank=True,
        help_text='Optional JSON wrapper key, e.g. "data".',
    )
    custom_headers_json = models.JSONField(default=dict, blank=True)
    failure_action = models.CharField(
        max_length=32,
        choices=FailureAction.choices,
        default=FailureAction.BLOCK,
    )
    message_rejected = models.TextField(
        "Message when API rejects (non-200)",
        blank=True,
        help_text="Shown to applicants. Placeholders: {{status}}, {{api_message}}. "
        "Leave blank for the default.",
    )
    message_unreachable = models.TextField(
        "Message when API is unreachable",
        blank=True,
        help_text="Shown when the validation service cannot be reached. Leave blank for the default.",
    )
    message_error = models.TextField(
        "Message when validation request fails",
        blank=True,
        help_text="Shown on unexpected errors calling the API. Leave blank for the default.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    MAX_APPLICANT_MESSAGE_LEN = 1000

    def __str__(self):
        return f"Submit validation · {self.form_id}"

    def has_secret(self) -> bool:
        return bool((self.secret_encrypted or "").strip())


class FormOutboundFieldMap(models.Model):
    class SourceType(models.TextChoices):
        FORM_FIELD = "form_field", _("Form field")
        APPLICANT = "applicant", _("Applicant (submitter account / profile)")
        SYSTEM = "system", _("System / workflow")
        CONSTANT = "constant", _("Constant")

    class Transform(models.TextChoices):
        NONE = "none", _("None")
        ISO_DATE = "iso_date", _("ISO date/time")
        BOOL_YES_NO = "bool_yes_no", _("Yes / no")
        JSON_ARRAY = "json_array", _("Split lines to JSON array")
        FILE_SIGNED_URL = "file_signed_url", _("File: signed download URL")
        FILE_FILENAME = "file_filename", _("File: filename only")
        FILE_DETAILS = "file_details", _("File: object (filename + signed URL)")

    config = models.ForeignKey(
        FormOutboundConfig,
        on_delete=models.CASCADE,
        related_name="field_maps",
    )
    external_key = models.CharField(max_length=120)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_ref = models.CharField(max_length=120, blank=True)
    transform = models.CharField(
        max_length=20,
        choices=Transform.choices,
        default=Transform.NONE,
    )
    required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["config", "external_key"],
                name="uniq_outbound_map_config_external_key",
            ),
        ]

    def __str__(self):
        return f"{self.external_key} ← {self.source_type}:{self.source_ref}"


class FormOutboundDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        RUNNING = "running", _("Running")
        SUCCESS = "success", _("Success")
        DEAD = "dead", _("Dead")

    config = models.ForeignKey(
        FormOutboundConfig,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="outbound_deliveries",
    )
    submission_event = models.ForeignKey(
        SubmissionEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbound_deliveries",
    )
    trigger = models.CharField(max_length=40, db_index=True)
    idempotency_key = models.CharField(max_length=36, unique=True, db_index=True)
    workflow_decision = models.CharField(max_length=32, blank=True)
    workflow_decision_comment = models.CharField(max_length=800, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    request_url = models.URLField(max_length=500, blank=True)
    request_headers_redacted = models.TextField(blank=True)
    request_body_redacted = models.TextField(blank=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body_truncated = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.trigger} · {self.submission_id} · {self.status}"


class MobileAuthToken(models.Model):
    """Bearer token for native mobile clients (``Authorization: Bearer …``)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_auth_tokens",
    )
    key = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"Mobile token · user={self.user_id}"


class MobilePushDevice(models.Model):
    """APNs or FCM device token for push notifications."""

    PLATFORM_IOS = "ios"
    PLATFORM_ANDROID = "android"
    PLATFORM_CHOICES = [
        (PLATFORM_IOS, "iOS"),
        (PLATFORM_ANDROID, "Android"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_push_devices",
    )
    platform = models.CharField(max_length=16, choices=PLATFORM_CHOICES, db_index=True)
    token = models.CharField(max_length=512, db_index=True)
    device_id = models.CharField(max_length=128, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "platform", "token"],
                name="mobile_push_device_user_platform_token_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"Push · {self.platform} · user={self.user_id}"


class MobilePushDevice(models.Model):
    """APNs / FCM device token for native mobile push notifications."""

    PLATFORM_IOS = "ios"
    PLATFORM_ANDROID = "android"
    PLATFORM_CHOICES = (
        (PLATFORM_IOS, "iOS"),
        (PLATFORM_ANDROID, "Android"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_push_devices",
    )
    platform = models.CharField(max_length=16, choices=PLATFORM_CHOICES)
    token = models.CharField(max_length=512, db_index=True)
    device_id = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        help_text="Optional stable client id (UUID).",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "platform", "token"],
                name="magicforms_mobile_push_device_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "platform", "-updated_at"]),
        ]

    def __str__(self):
        return f"Push · {self.platform} · user={self.user_id}"


class ActivityLog(models.Model):
    """Audit trail of studio, public web, and mobile API requests."""

    class Channel(models.TextChoices):
        WEB_MANAGE = "web_manage", _("Workspace")
        WEB_PUBLIC = "web_public", _("Public site")
        API_MOBILE = "api_mobile", _("Mobile API")
        WEB_OTHER = "web_other", _("Web")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    username = models.CharField(max_length=150, blank=True, db_index=True)
    is_staff_actor = models.BooleanField(default=False, db_index=True)
    channel = models.CharField(max_length=32, choices=Channel.choices, db_index=True)
    http_method = models.CharField(max_length=16, blank=True, db_index=True)
    path = models.CharField(max_length=500, db_index=True)
    query_string = models.CharField(max_length=500, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    view_name = models.CharField(max_length=200, blank=True, db_index=True)
    summary = models.CharField(max_length=500, blank=True)
    entity_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    object_type = models.CharField(max_length=120, blank=True, db_index=True)
    object_id = models.CharField(max_length=64, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "activity log"
        verbose_name_plural = "activity logs"
        indexes = [
            models.Index(fields=["-created_at", "channel"]),
            models.Index(fields=["username", "-created_at"]),
        ]

    def __str__(self):
        who = self.username or _("(anonymous)")
        return f"{who} · {self.http_method} {self.path} · {self.created_at}"
