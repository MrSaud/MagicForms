from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0064_form_intro_list_style"),
    ]

    operations = [
        migrations.AddField(
            model_name="formfield",
            name="validation_unique_value",
            field=models.BooleanField(
                default=False,
                help_text="When on, reject a new submission if this field’s answer was already submitted "
                "on this form (e.g. national ID or email). Not for file uploads or checklist fields.",
            ),
        ),
    ]
