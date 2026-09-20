from django.db import migrations, models

AREAS = (
    "manage_people",
    "manage_forms",
    "view_responses",
    "export_responses",
    "manage_delegations",
    "manage_categories",
    "manage_entity_settings",
)


def copy_legacy_permissions(apps, schema_editor):
    EntityMembership = apps.get_model("magicforms", "EntityMembership")
    for row in EntityMembership.objects.all():
        update = {}
        for area in AREAS:
            legacy = bool(getattr(row, area, False))
            update[f"{area}_read"] = legacy
            update[f"{area}_write"] = legacy
        EntityMembership.objects.filter(pk=row.pk).update(**update)


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0080_entity_membership_permissions"),
    ]

    operations = [
        *[
            migrations.AddField(
                model_name="entitymembership",
                name=f"{area}_read",
                field=models.BooleanField(default=False),
            )
            for area in AREAS
        ],
        *[
            migrations.AddField(
                model_name="entitymembership",
                name=f"{area}_write",
                field=models.BooleanField(default=False),
            )
            for area in AREAS
        ],
        migrations.RunPython(copy_legacy_permissions, migrations.RunPython.noop),
        *[
            migrations.RemoveField(model_name="entitymembership", name=area)
            for area in AREAS
        ],
    ]
