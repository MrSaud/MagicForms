from django.db import migrations, models
import django.core.validators
import magicforms.models


class Migration(migrations.Migration):
    dependencies = [
        ("magicforms", "0060_form_intro_page"),
    ]

    operations = [
        migrations.CreateModel(
            name="FormIntroSlide",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "image",
                    models.ImageField(
                        max_length=500,
                        upload_to=magicforms.models.form_intro_slide_upload_to,
                        validators=[
                            django.core.validators.FileExtensionValidator(
                                allowed_extensions=["png", "jpg", "jpeg", "gif", "webp"]
                            )
                        ],
                        verbose_name="Slideshow image",
                    ),
                ),
                (
                    "caption",
                    models.CharField(
                        blank=True,
                        help_text="Optional text shown under the image in the slideshow.",
                        max_length=255,
                        verbose_name="Caption",
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(db_index=True, default=0)),
                (
                    "form",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="intro_slides",
                        to="magicforms.form",
                    ),
                ),
            ],
            options={
                "verbose_name": "Information page slide",
                "verbose_name_plural": "Information page slides",
                "ordering": ["sort_order", "id"],
            },
        ),
    ]
