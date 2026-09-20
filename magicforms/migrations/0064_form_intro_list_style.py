from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("magicforms", "0063_form_intro_show_capacity"),
    ]

    operations = [
        migrations.AddField(
            model_name="form",
            name="intro_details_list_style",
            field=models.CharField(
                choices=[("bullet", "Bullet points"), ("ordered", "Numbered list")],
                default="bullet",
                help_text="How highlight lines appear on the announcement page.",
                max_length=16,
                verbose_name="Highlights list style",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="intro_rules_list_style",
            field=models.CharField(
                choices=[("bullet", "Bullet points"), ("ordered", "Numbered list")],
                default="bullet",
                help_text="How guideline lines appear on the announcement page.",
                max_length=16,
                verbose_name="Guidelines list style",
            ),
        ),
    ]
