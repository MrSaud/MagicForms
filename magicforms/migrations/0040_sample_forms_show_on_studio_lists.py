# Show starter sample forms on the studio dashboard (they were hide_from_form_lists=True).

from django.db import migrations


def forwards(apps, schema_editor):
    from magicforms.sample_forms_library import SAMPLE_FORM_SLUGS

    Form = apps.get_model("magicforms", "Form")
    Form.objects.filter(slug__in=SAMPLE_FORM_SLUGS).update(hide_from_form_lists=False)


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0039_sample_forms_all_entities"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
