import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("magicforms", "0061_form_intro_slide"),
    ]

    operations = [
        migrations.AddField(
            model_name="form",
            name="intro_venue_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("in_person", "In person"),
                    ("online", "Online"),
                    ("hybrid", "Hybrid"),
                ],
                help_text="Optional. In person, online, or hybrid.",
                max_length=20,
                verbose_name="Format",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_location",
            field=models.CharField(
                blank=True,
                help_text="Optional address, room, or online access note.",
                max_length=500,
                verbose_name="Venue or location",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_map_url",
            field=models.URLField(
                blank=True,
                help_text="Optional link to maps or directions.",
                max_length=500,
                verbose_name="Map link",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_contact_name",
            field=models.CharField(
                blank=True,
                help_text="Optional organizer or point of contact.",
                max_length=200,
                verbose_name="Contact name",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_contact_email",
            field=models.EmailField(
                blank=True,
                max_length=254,
                verbose_name="Contact email",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_contact_phone",
            field=models.CharField(
                blank=True,
                max_length=80,
                verbose_name="Contact phone",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_fee",
            field=models.CharField(
                blank=True,
                help_text='Optional, e.g. "Free" or "25 KWD".',
                max_length=120,
                verbose_name="Registration fee",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_capacity",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Optional maximum registrations. Remaining seats are shown on the announcement page.",
                null=True,
                verbose_name="Capacity (seats)",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_apply_button_label",
            field=models.CharField(
                blank=True,
                help_text='Optional call-to-action, e.g. "Register now". Defaults to "Apply now".',
                max_length=80,
                verbose_name="Apply button label",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_video_url",
            field=models.URLField(
                blank=True,
                help_text="Optional YouTube or Vimeo link (embedded when supported).",
                max_length=500,
                verbose_name="Featured video URL",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="intro_page_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Off by default. When on, applicants see your announcement first, then apply.",
                verbose_name="Show announcement page before applying",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="intro_title",
            field=models.CharField(
                blank=True,
                help_text="Optional. Defaults to the form title if blank.",
                max_length=255,
                verbose_name="Headline",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="intro_subtitle",
            field=models.CharField(
                blank=True,
                help_text="Optional short line under the headline.",
                max_length=400,
                verbose_name="Tagline",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="intro_description",
            field=models.TextField(
                blank=True,
                help_text="Optional. Plain text or simple HTML (bold, links, lists).",
                verbose_name="Message",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="intro_details",
            field=models.TextField(
                blank=True,
                help_text="Optional. One highlight per line (shown as bullets).",
                verbose_name="Highlights",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="intro_attachment",
            field=models.FileField(
                blank=True,
                help_text="Optional PDF download (brochure, instructions, etc.).",
                max_length=500,
                upload_to="form_intro_attachments/%Y/%m/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["pdf"]
                    )
                ],
                verbose_name="Brochure (PDF)",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="intro_event_start",
            field=models.DateTimeField(
                blank=True,
                help_text="Optional schedule start.",
                null=True,
                verbose_name="Starts",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="intro_event_end",
            field=models.DateTimeField(
                blank=True,
                help_text="Optional schedule end.",
                null=True,
                verbose_name="Ends",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="intro_rules",
            field=models.TextField(
                blank=True,
                help_text="Optional. One guideline per line.",
                verbose_name="Guidelines",
            ),
        ),
    ]
