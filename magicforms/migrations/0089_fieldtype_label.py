from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0088_alter_submissionuserhighlight_color"),
    ]

    operations = [
        migrations.AlterField(
            model_name="formfield",
            name="field_type",
            field=models.CharField(
                choices=[
                    ("text", "Short text"),
                    ("textarea", "Paragraph"),
                    ("email", "Email"),
                    ("number", "Number"),
                    ("date", "Date"),
                    ("select", "Dropdown"),
                    ("radio", "Radio buttons"),
                    ("checkbox", "Checkbox"),
                    ("checklist", "Checklist"),
                    ("file", "File upload"),
                    ("hint", "Hint (information only)"),
                    ("label", "Label (display text only)"),
                ],
                default="text",
                max_length=32,
            ),
        ),
    ]
