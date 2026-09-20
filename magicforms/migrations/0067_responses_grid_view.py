import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0066_user_submission_task"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ResponsesGridView",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("column_keys", models.JSONField(blank=True, default=list)),
                ("is_default", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "form",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="responses_grid_views",
                        to="magicforms.form",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="responses_grid_views_owned",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ResponsesGridViewShare",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "shared_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="responses_grid_views_shared_out",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="responses_grid_views_shared",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "view",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shares",
                        to="magicforms.responsesgridview",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="responsesgridview",
            constraint=models.UniqueConstraint(
                fields=("owner", "form", "name"),
                name="uniq_mf_responses_grid_view_owner_form_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="responsesgridviewshare",
            constraint=models.UniqueConstraint(
                fields=("view", "user"),
                name="uniq_mf_responses_grid_view_share_view_user",
            ),
        ),
    ]
