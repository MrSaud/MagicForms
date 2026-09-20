import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0068_entity_email_notifications"),
    ]

    operations = [
        migrations.CreateModel(
            name="EntityEmailNotificationBehavior",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notify_on_submit", models.BooleanField(default=True, verbose_name="Email applicant when form is submitted")),
                ("notify_on_accept", models.BooleanField(default=True, verbose_name="Email applicant when workflow is completed (accepted)")),
                ("notify_on_reject", models.BooleanField(default=True, verbose_name="Email applicant when workflow is rejected")),
                ("notify_on_step_approved", models.BooleanField(default=False, verbose_name="Email applicant on each intermediate approval step")),
                ("staff_contact_use_template", models.BooleanField(default=True, verbose_name="Prefill “Email applicant” with staff contact template")),
                (
                    "entity",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_notification_behavior",
                        to="magicforms.entity",
                    ),
                ),
            ],
            options={
                "verbose_name": "Email notification behavior",
                "verbose_name_plural": "Email notification behaviors",
            },
        ),
        migrations.CreateModel(
            name="EntityEmailNotificationTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("submitted", "Form submitted"),
                            ("accepted", "Workflow accepted (completed)"),
                            ("rejected", "Workflow rejected"),
                            ("staff_contact", "Staff contact (manual email)"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("subject", models.CharField(max_length=200)),
                ("body", models.TextField()),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "entity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_notification_templates",
                        to="magicforms.entity",
                    ),
                ),
            ],
            options={
                "ordering": ["entity_id", "kind"],
            },
        ),
        migrations.AddConstraint(
            model_name="entityemailnotificationtemplate",
            constraint=models.UniqueConstraint(
                fields=("entity", "kind"),
                name="uniq_mf_entity_email_template_entity_kind",
            ),
        ),
    ]
