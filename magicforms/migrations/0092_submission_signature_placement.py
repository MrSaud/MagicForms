import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import magicforms.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("magicforms", "0091_form_layout_direction"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubmissionSignaturePlacement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_index", models.PositiveIntegerField(default=0)),
                ("x", models.FloatField()),
                ("y", models.FloatField()),
                ("width", models.FloatField(default=0.22)),
                (
                    "image",
                    models.FileField(
                        max_length=500,
                        upload_to=magicforms.models.submission_signature_placement_upload_to,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="submission_signature_placements",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="signature_placements",
                        to="magicforms.formsubmission",
                    ),
                ),
            ],
            options={"ordering": ["page_index", "created_at", "id"]},
        ),
    ]
