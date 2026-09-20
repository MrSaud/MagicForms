from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0072_form_submit_validation_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="formsubmitvalidationconfig",
            name="message_rejected",
            field=models.TextField(
                blank=True,
                help_text="Shown to applicants. Placeholders: {{status}}, {{api_message}}. Leave blank for the default.",
                verbose_name="Message when API rejects (non-200)",
            ),
        ),
        migrations.AddField(
            model_name="formsubmitvalidationconfig",
            name="message_unreachable",
            field=models.TextField(
                blank=True,
                help_text="Shown when the validation service cannot be reached. Leave blank for the default.",
                verbose_name="Message when API is unreachable",
            ),
        ),
        migrations.AddField(
            model_name="formsubmitvalidationconfig",
            name="message_error",
            field=models.TextField(
                blank=True,
                help_text="Shown on unexpected errors calling the API. Leave blank for the default.",
                verbose_name="Message when validation request fails",
            ),
        ),
    ]
