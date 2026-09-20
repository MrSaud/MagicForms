# Multi-entity tenancy: Entity, memberships, scoped categories/forms/delegations.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def forwards_org_data(apps, schema_editor):
    Entity = apps.get_model("magicforms", "Entity")
    FormCategory = apps.get_model("magicforms", "FormCategory")
    Form = apps.get_model("magicforms", "Form")
    WorkflowDelegation = apps.get_model("magicforms", "WorkflowDelegation")
    EntityMembership = apps.get_model("magicforms", "EntityMembership")
    User = apps.get_model(settings.AUTH_USER_MODEL)

    default, _ = Entity.objects.get_or_create(
        slug="default",
        defaults={"name": "Default organization", "is_active": True},
    )

    for cat in FormCategory.objects.all():
        if cat.entity_id is None:
            cat.entity_id = default.pk
            cat.save(update_fields=["entity_id"])

    for form in Form.objects.all():
        if form.entity_id is None:
            if form.category_id:
                c = FormCategory.objects.get(pk=form.category_id)
                form.entity_id = c.entity_id
            else:
                form.entity_id = default.pk
            form.save(update_fields=["entity_id"])

    for d in WorkflowDelegation.objects.all():
        if d.entity_id is None:
            d.entity_id = default.pk
            d.save(update_fields=["entity_id"])

    staff_ids = User.objects.filter(is_staff=True).values_list("pk", flat=True)
    for uid in staff_ids:
        EntityMembership.objects.get_or_create(user_id=uid, entity_id=default.pk)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("magicforms", "0017_workflow_delegation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Entity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(db_index=True, max_length=80, unique=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name_plural": "Entities",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="EntityMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "entity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="magicforms.entity",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entity_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["entity__name", "user__username"],
            },
        ),
        migrations.AddConstraint(
            model_name="entitymembership",
            constraint=models.UniqueConstraint(
                fields=("user", "entity"),
                name="uniq_entity_membership_user_entity",
            ),
        ),
        migrations.AddField(
            model_name="formcategory",
            name="entity",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="categories",
                to="magicforms.entity",
            ),
        ),
        migrations.AddField(
            model_name="form",
            name="entity",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="forms",
                to="magicforms.entity",
            ),
        ),
        migrations.AddField(
            model_name="workflowdelegation",
            name="entity",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="workflow_delegations",
                to="magicforms.entity",
            ),
        ),
        migrations.RunPython(forwards_org_data, noop_reverse),
        migrations.AlterField(
            model_name="formcategory",
            name="entity",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="categories",
                to="magicforms.entity",
            ),
        ),
        migrations.AlterField(
            model_name="formcategory",
            name="name",
            field=models.CharField(max_length=120),
        ),
        migrations.AlterField(
            model_name="formcategory",
            name="slug",
            field=models.SlugField(blank=True, db_index=True, max_length=80),
        ),
        migrations.AddConstraint(
            model_name="formcategory",
            constraint=models.UniqueConstraint(fields=("entity", "slug"), name="uniq_formcategory_entity_slug"),
        ),
        migrations.AddConstraint(
            model_name="formcategory",
            constraint=models.UniqueConstraint(fields=("entity", "name"), name="uniq_formcategory_entity_name"),
        ),
        migrations.AlterField(
            model_name="form",
            name="entity",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="forms",
                to="magicforms.entity",
            ),
        ),
        migrations.AlterField(
            model_name="form",
            name="slug",
            field=models.SlugField(db_index=True, max_length=120),
        ),
        migrations.AddConstraint(
            model_name="form",
            constraint=models.UniqueConstraint(fields=("entity", "slug"), name="uniq_form_entity_slug"),
        ),
        migrations.AlterField(
            model_name="workflowdelegation",
            name="entity",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="workflow_delegations",
                to="magicforms.entity",
            ),
        ),
    ]
