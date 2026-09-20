import django.core.validators
from django.db import migrations, models


def default_theme_presets():
    return [
        {"primary": "#0071e3", "secondary": "", "background": ""},
        {"primary": "#0071e3", "secondary": "", "background": ""},
        {"primary": "#0071e3", "secondary": "", "background": ""},
    ]


def copy_legacy_theme_to_presets(apps, schema_editor):
    Entity = apps.get_model("magicforms", "Entity")
    for ent in Entity.objects.iterator():
        p = (getattr(ent, "theme_primary", None) or "#0071e3").strip()[:7]
        s = (getattr(ent, "theme_secondary", None) or "").strip()[:7]
        b = (getattr(ent, "theme_background", None) or "").strip()[:7]
        ent.theme_presets = [
            {"primary": p, "secondary": s, "background": b},
            {"primary": "#0071e3", "secondary": "", "background": ""},
            {"primary": "#0071e3", "secondary": "", "background": ""},
        ]
        ent.active_theme_index = 0
        ent.save(update_fields=["theme_presets", "active_theme_index"])


class Migration(migrations.Migration):
    dependencies = [
        ("magicforms", "0042_formfield_options_layout"),
    ]

    operations = [
        migrations.AddField(
            model_name="entity",
            name="theme_presets",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="entity",
            name="active_theme_index",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(2),
                ],
            ),
        ),
        migrations.RunPython(copy_legacy_theme_to_presets, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="entity",
            name="theme_presets",
            field=models.JSONField(default=default_theme_presets),
        ),
        migrations.RemoveField(
            model_name="entity",
            name="theme_primary",
        ),
        migrations.RemoveField(
            model_name="entity",
            name="theme_secondary",
        ),
        migrations.RemoveField(
            model_name="entity",
            name="theme_background",
        ),
    ]
