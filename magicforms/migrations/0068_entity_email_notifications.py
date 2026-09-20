from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0067_responses_grid_view"),
    ]

    operations = [
        migrations.AddField(
            model_name="entity",
            name="email_notifications_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When on, staff can send email to applicants from the submission page using this organization's SMTP.",
                verbose_name="Email notifications enabled",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="email_from_address",
            field=models.CharField(
                blank=True,
                help_text='Sender for outbound mail, e.g. "HR Team <noreply@yourorg.com>" or plain email@yourorg.com.',
                max_length=254,
                verbose_name="Email From address",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="email_reply_to",
            field=models.EmailField(
                blank=True,
                help_text="Optional default Reply-To on applicant emails (staff user email is also added when set).",
                verbose_name="Default Reply-To",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="email_smtp_host",
            field=models.CharField(blank=True, max_length=255, verbose_name="SMTP host"),
        ),
        migrations.AddField(
            model_name="entity",
            name="email_smtp_port",
            field=models.PositiveIntegerField(
                default=587,
                help_text="Usually 587 (STARTTLS) or 465 (SSL).",
                verbose_name="SMTP port",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="email_smtp_use_tls",
            field=models.BooleanField(
                default=True,
                help_text="Typical for port 587. Turn off when using SSL on port 465.",
                verbose_name="SMTP use TLS (STARTTLS)",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="email_smtp_use_ssl",
            field=models.BooleanField(
                default=False,
                help_text="Typical for port 465. Do not enable together with STARTTLS.",
                verbose_name="SMTP use SSL",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="email_smtp_username",
            field=models.CharField(blank=True, max_length=255, verbose_name="SMTP username"),
        ),
        migrations.AddField(
            model_name="entity",
            name="email_smtp_password",
            field=models.CharField(
                blank=True,
                help_text="Stored on the organization record. Leave blank when editing to keep the current password.",
                max_length=512,
                verbose_name="SMTP password",
            ),
        ),
    ]
