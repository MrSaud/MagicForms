import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0055_workflowdelegation_directory_api"),
    ]

    operations = [
        migrations.CreateModel(
            name="FormOutboundConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=False)),
                ("endpoint_url", models.URLField(blank=True, max_length=500)),
                ("timeout_seconds", models.PositiveSmallIntegerField(default=20)),
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
                ("trigger_submitted", models.BooleanField(default=True, verbose_name="On form submit")),
                ("trigger_step_approved", models.BooleanField(default=False, verbose_name="On step approved")),
                (
                    "trigger_workflow_completed",
                    models.BooleanField(default=True, verbose_name="On workflow completed"),
                ),
                (
                    "trigger_workflow_rejected",
                    models.BooleanField(default=True, verbose_name="On workflow rejected"),
                ),
                (
                    "payload_root_key",
                    models.CharField(
                        blank=True,
                        help_text='Optional JSON wrapper key, e.g. "data".',
                        max_length=64,
                    ),
                ),
                ("custom_headers_json", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "form",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outbound_config",
                        to="magicforms.form",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="FormOutboundFieldMap",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_key", models.CharField(max_length=120)),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("form_field", "Form field"),
                            ("system", "System / workflow"),
                            ("constant", "Constant"),
                        ],
                        max_length=20,
                    ),
                ),
                ("source_ref", models.CharField(blank=True, max_length=120)),
                (
                    "transform",
                    models.CharField(
                        choices=[
                            ("none", "None"),
                            ("iso_date", "ISO date/time"),
                            ("bool_yes_no", "Yes / no"),
                            ("json_array", "Split lines to JSON array"),
                        ],
                        default="none",
                        max_length=20,
                    ),
                ),
                ("required", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(db_index=True, default=0)),
                (
                    "config",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="field_maps",
                        to="magicforms.formoutboundconfig",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
        migrations.CreateModel(
            name="FormOutboundDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trigger", models.CharField(db_index=True, max_length=40)),
                ("idempotency_key", models.CharField(db_index=True, max_length=36, unique=True)),
                ("workflow_decision", models.CharField(blank=True, max_length=32)),
                ("workflow_decision_comment", models.CharField(blank=True, max_length=800)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("dead", "Dead"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("next_retry_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("request_url", models.URLField(blank=True, max_length=500)),
                ("request_headers_redacted", models.TextField(blank=True)),
                ("request_body_redacted", models.TextField(blank=True)),
                ("response_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_body_truncated", models.TextField(blank=True)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "config",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="magicforms.formoutboundconfig",
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outbound_deliveries",
                        to="magicforms.formsubmission",
                    ),
                ),
                (
                    "submission_event",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="outbound_deliveries",
                        to="magicforms.submissionevent",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="formoutboundfieldmap",
            constraint=models.UniqueConstraint(
                fields=("config", "external_key"),
                name="uniq_outbound_map_config_external_key",
            ),
        ),
    ]
