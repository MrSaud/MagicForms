# Return starter templates to the shared pool (created_by unset).

from django.db import migrations


def forwards(apps, schema_editor):
    from magicforms.sample_forms_library import SAMPLE_FORM_SLUGS

    Form = apps.get_model("magicforms", "Form")
    Form.objects.filter(slug__in=SAMPLE_FORM_SLUGS).update(created_by=None)


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0074_sample_forms_assign_owners"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
