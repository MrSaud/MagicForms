from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("magicforms", "0062_form_intro_announcement_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="form",
            name="intro_show_capacity",
            field=models.BooleanField(
                default=True,
                help_text="When capacity is set, show seats left on the announcement page. "
                "Turn off to hide capacity there while keeping the limit for your own reference.",
                verbose_name="Show remaining seats on announcement page",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="intro_capacity",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Optional maximum registrations.",
                null=True,
                verbose_name="Capacity (seats)",
            ),
        ),
    ]
