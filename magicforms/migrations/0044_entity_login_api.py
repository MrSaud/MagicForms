from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("magicforms", "0043_entity_theme_presets"),
    ]

    operations = [
        migrations.AddField(
            model_name="entity",
            name="login_api_endpoint",
            field=models.URLField(
                blank=True,
                max_length=500,
                help_text="HTTPS URL of the directory login API (JSON POST with username and password).",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="login_api_token",
            field=models.CharField(
                blank=True,
                max_length=512,
                help_text="Bearer token sent as Authorization when calling the login API.",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="login_api_active",
            field=models.BooleanField(
                default=False,
                help_text="When on, /manage/login/ tries this organization’s API before Django authentication.",
            ),
        ),
    ]
