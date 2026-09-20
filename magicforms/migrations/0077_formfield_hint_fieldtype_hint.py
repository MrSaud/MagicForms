from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0076_alter_workflowstep_assigned_users"),
    ]

    operations = [
        migrations.AddField(
            model_name="formfield",
            name="hint",
            field=models.TextField(
                blank=True,
                help_text="Optional guidance on the live form (under the label). Not stored as an answer.",
            ),
        ),
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
                ],
                default="text",
                max_length=32,
            ),
        ),
    ]
