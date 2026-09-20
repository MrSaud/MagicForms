from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0059_entity_page_logo_verbose_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="form",
            name="intro_page_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When on, respondents see a description page first, then continue to the submission form.",
                verbose_name="Show information page before the form",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_title",
            field=models.CharField(
                blank=True,
                help_text="e.g. Annual conference registration",
                max_length=255,
                verbose_name="Information page title",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_subtitle",
            field=models.CharField(
                blank=True,
                max_length=400,
                verbose_name="Information page subtitle",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_description",
            field=models.TextField(
                blank=True,
                help_text="Overview shown above the details list.",
                verbose_name="Information page description",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_details",
            field=models.TextField(
                blank=True,
                help_text="One item per line. Shown as a bullet list on the information page.",
                verbose_name="Details (bullet list)",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_attachment",
            field=models.FileField(
                blank=True,
                help_text="Optional PDF for applicants to download (event brochure, instructions, etc.).",
                max_length=500,
                upload_to="form_intro_attachments/%Y/%m/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["pdf"]
                    )
                ],
                verbose_name="Attachment (PDF)",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_event_start",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Event start"),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_event_end",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Event end"),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_rules",
            field=models.TextField(
                blank=True,
                help_text="One rule per line. Shown as a bullet list before the apply button.",
                verbose_name="Rules (bullet list)",
            ),
        ),
    ]
