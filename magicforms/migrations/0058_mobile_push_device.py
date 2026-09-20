from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0057_mobile_auth_token"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MobilePushDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("platform", models.CharField(choices=[("ios", "iOS"), ("android", "Android")], db_index=True, max_length=16)),
                ("token", models.CharField(db_index=True, max_length=512)),
                ("device_id", models.CharField(blank=True, default="", max_length=128)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mobile_push_devices",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "is_active"], name="magicforms_m_user_id_6e0f0a_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="mobilepushdevice",
            constraint=models.UniqueConstraint(
                fields=("user", "platform", "token"),
                name="mobile_push_device_user_platform_token_uniq",
            ),
        ),
    ]
