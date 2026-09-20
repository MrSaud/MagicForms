import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0071_user_submission_task_due_date"),
    ]

    operations = [
        migrations.CreateModel(
            name="FormSubmitValidationConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=False)),
                ("endpoint_url", models.URLField(blank=True, max_length=500)),
                ("timeout_seconds", models.PositiveSmallIntegerField(default=15)),
                (
                    "auth_type",
                    models.CharField(
                        choices=[
                            ("none", "None"),
                            ("bearer", "Bearer token"),
                            ("header", "Custom header"),
                            ("basic", "Basic (secret is base64 user:pass or token)"),
                            ("hmac_sha256", "HMAC-SHA256 (secret + timestamp)"),
                        ],
                        default="bearer",
                        max_length=32,
                    ),
                ),
                (
                    "auth_header_name",
                    models.CharField(
                        blank=True,
                        default="Authorization",
                        help_text="Header for Bearer/custom auth (default Authorization).",
                        max_length=64,
                    ),
                ),
                ("secret_encrypted", models.TextField(blank=True)),
                ("hmac_header_name", models.CharField(blank=True, default="X-Signature", max_length=64)),
                (
                    "payload_root_key",
                    models.CharField(
                        blank=True,
                        help_text='Optional JSON wrapper key, e.g. "data".',
                        max_length=64,
                    ),
                ),
                ("custom_headers_json", models.JSONField(blank=True, default=dict)),
                (
                    "failure_action",
                    models.CharField(
                        choices=[
                            ("block", "Block submit when the API does not return HTTP 200"),
                            (
                                "allow_continue",
                                "Let the respondent choose to submit anyway",
                            ),
                        ],
                        default="block",
                        max_length=32,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "form",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submit_validation_config",
                        to="magicforms.form",
                    ),
                ),
            ],
        ),
    ]
