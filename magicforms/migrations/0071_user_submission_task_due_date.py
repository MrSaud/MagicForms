from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0070_alter_formintroslide_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="usersubmissiontask",
            name="due_date",
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text="Optional follow-up date for this task.",
                null=True,
                verbose_name="Deadline",
            ),
        ),
    ]
