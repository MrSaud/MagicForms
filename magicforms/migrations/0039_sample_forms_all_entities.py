# Data migration: ensure sample HR / Finance / operations forms exist for every organization.

from django.db import migrations


def forwards(apps, schema_editor):
    from magicforms.sample_forms_library import load_sample_forms

    load_sample_forms(apps)


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0038_sample_business_forms"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
