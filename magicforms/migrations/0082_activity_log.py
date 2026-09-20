import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0081_entity_membership_permissions_read_write"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ActivityLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("username", models.CharField(blank=True, db_index=True, max_length=150)),
                ("is_staff_actor", models.BooleanField(db_index=True, default=False)),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("web_manage", "Studio"),
                            ("web_public", "Public site"),
                            ("api_mobile", "Mobile API"),
                            ("web_other", "Web"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("http_method", models.CharField(blank=True, db_index=True, max_length=16)),
                ("path", models.CharField(db_index=True, max_length=500)),
                ("query_string", models.CharField(blank=True, max_length=500)),
                ("status_code", models.PositiveSmallIntegerField(blank=True, db_index=True, null=True)),
                ("view_name", models.CharField(blank=True, db_index=True, max_length=200)),
                ("summary", models.CharField(blank=True, max_length=500)),
                ("entity_id", models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ("object_type", models.CharField(blank=True, db_index=True, max_length=120)),
                ("object_id", models.CharField(blank=True, db_index=True, max_length=64)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=300)),
                ("duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("extra", models.JSONField(blank=True, default=dict)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activity_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "activity log",
                "verbose_name_plural": "activity logs",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["-created_at", "channel"], name="magicforms__created_b8e0f6_idx"),
                    models.Index(fields=["username", "-created_at"], name="magicforms__usernam_4a8c2d_idx"),
                ],
            },
        ),
    ]
