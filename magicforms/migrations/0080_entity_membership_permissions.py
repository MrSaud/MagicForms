from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0079_submission_timeline_share_message_viewed"),
    ]

    operations = [
        migrations.AddField(
            model_name="entitymembership",
            name="manage_people",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="entitymembership",
            name="manage_forms",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="entitymembership",
            name="view_responses",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="entitymembership",
            name="export_responses",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="entitymembership",
            name="manage_delegations",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="entitymembership",
            name="manage_categories",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="entitymembership",
            name="manage_entity_settings",
            field=models.BooleanField(default=False),
        ),
    ]
