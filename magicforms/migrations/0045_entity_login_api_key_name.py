from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("magicforms", "0044_entity_login_api"),
    ]

    operations = [
        migrations.AddField(
            model_name="entity",
            name="login_api_key_name",
            field=models.CharField(
                blank=True,
                max_length=64,
                verbose_name="API key name",
                help_text="HTTP header used for the API secret (blank = Authorization with Bearer prefix).",
            ),
        ),
    ]
