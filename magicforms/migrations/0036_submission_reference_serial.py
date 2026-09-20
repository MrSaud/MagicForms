# Generated manually for UUID -> decimal serial reference_token

import random

from django.db import migrations, models
from django.utils import timezone


def _allocate_serial_for_row(dt, seen, FormSubmission, field_name, pk):
    if dt is None:
        dt = timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    dt_local = timezone.localtime(dt)
    for _ in range(500):
        candidate = dt_local.strftime("%y%m%d%H%M") + f"{random.randint(0, 999999):06d}"
        if candidate in seen:
            continue
        if (
            FormSubmission.objects.filter(**{field_name: candidate})
            .exclude(pk=pk)
            .exists()
        ):
            continue
        seen.add(candidate)
        return candidate
    msg = f"Could not allocate unique submission serial for pk={pk}"
    raise RuntimeError(msg)


def forwards_fill_reference_serial(apps, schema_editor):
    FormSubmission = apps.get_model("magicforms", "FormSubmission")
    seen: set[str] = set()
    for sub in FormSubmission.objects.order_by("pk").iterator():
        serial = _allocate_serial_for_row(
            sub.submitted_at, seen, FormSubmission, "reference_serial", sub.pk
        )
        sub.reference_serial = serial
        sub.save(update_fields=["reference_serial"])


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0035_formlogo_header_slot_meta"),
    ]

    operations = [
        migrations.AddField(
            model_name="formsubmission",
            name="reference_serial",
            field=models.CharField(editable=False, max_length=20, null=True),
        ),
        migrations.RunPython(forwards_fill_reference_serial, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="formsubmission",
            name="reference_token",
        ),
        migrations.RenameField(
            model_name="formsubmission",
            old_name="reference_serial",
            new_name="reference_token",
        ),
        migrations.AlterField(
            model_name="formsubmission",
            name="reference_token",
            field=models.CharField(editable=False, max_length=20, unique=True),
        ),
    ]
