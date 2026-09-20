from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0090_fieldtype_break"),
    ]

    operations = [
        migrations.AddField(
            model_name="form",
            name="layout_direction",
            field=models.CharField(
                choices=[
                    ("auto", "Follow the site language"),
                    ("rtl", "Right to left (Arabic)"),
                    ("ltr", "Left to right (English)"),
                ],
                default="auto",
                help_text=(
                    "Text direction of the public form pages. \u201cFollow the site language\u201d switches with the "
                    "visitor's language; RTL or LTR pins the layout regardless of language."
                ),
                max_length=4,
                verbose_name="Default layout direction",
            ),
        ),
    ]
