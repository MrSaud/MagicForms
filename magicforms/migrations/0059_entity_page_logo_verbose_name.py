from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0058_mobile_push_device"),
    ]

    operations = [
        migrations.AlterField(
            model_name="entity",
            name="page_logo",
            field=models.FileField(
                blank=True,
                help_text="Optional image for the studio banner, public portal, mobile app, and directory card. For PNG, JPEG, and WebP uploads, very light backgrounds are removed automatically (stored as PNG). SVG and GIF are not altered.",
                max_length=500,
                upload_to="entity_page_logos/%Y/%m/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "svg"]
                    )
                ],
                verbose_name="Organization logo",
            ),
        ),
    ]
