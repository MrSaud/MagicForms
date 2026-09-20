# Entity public portal: logo, copy, theme colors, notifications toggle, etc.

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0018_entities_and_scoping"),
    ]

    operations = [
        migrations.AddField(
            model_name="entity",
            name="footer_note",
            field=models.TextField(
                blank=True,
                help_text="Small print or disclaimer at the bottom of the public portal.",
                max_length=2000,
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="home_news",
            field=models.TextField(
                blank=True,
                help_text="News or announcements for the public portal (plain text; line breaks are kept).",
                verbose_name="Home / portal news",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="notifications_enabled",
            field=models.BooleanField(
                default=True,
                help_text="When off, automated notification hooks for this organization are skipped.",
                verbose_name="Notifications enabled",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="page_logo",
            field=models.FileField(
                blank=True,
                help_text="Optional image shown on this organization’s public portal and directory card.",
                max_length=500,
                upload_to="entity_page_logos/%Y/%m/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "svg"],
                    )
                ],
                verbose_name="Portal logo",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="portal_meta_note",
            field=models.CharField(
                blank=True,
                help_text="Internal note (not shown publicly); e.g. billing reference or launch checklist.",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="public_contact_email",
            field=models.EmailField(
                blank=True,
                help_text="Optional contact shown on the public portal.",
                max_length=254,
                verbose_name="Public contact email",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="public_site_tagline",
            field=models.CharField(
                blank=True,
                help_text="Short line under the title on the public portal.",
                max_length=400,
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="public_site_title",
            field=models.CharField(
                blank=True,
                help_text="Browser tab and portal header. Leave blank to use the organization name.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="show_on_public_directory",
            field=models.BooleanField(
                default=True,
                help_text="Show this organization on the global home page directory.",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="theme_background",
            field=models.CharField(
                blank=True,
                help_text="Optional very light page background tint (hex, e.g. #f5f5f7).",
                max_length=7,
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="theme_primary",
            field=models.CharField(
                default="#0071e3",
                help_text="Primary brand color (CSS hex, e.g. #0071e3).",
                max_length=7,
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="theme_secondary",
            field=models.CharField(
                blank=True,
                help_text="Secondary accent (hex). Blank uses the primary color.",
                max_length=7,
            ),
        ),
    ]
