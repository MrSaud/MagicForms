from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0089_fieldtype_label"),
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
                    ("break", "Break (line spacer)"),
                ],
                default="text",
                max_length=32,
            ),
        ),
    ]
