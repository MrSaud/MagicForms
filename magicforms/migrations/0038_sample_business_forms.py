# Data migration: HR / Finance / operations sample forms (draft, hidden from public lists).

from django.db import migrations


def forwards(apps, schema_editor):
    from magicforms.sample_forms_library import load_sample_forms

    load_sample_forms(apps)


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0037_related_form_terminology"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
