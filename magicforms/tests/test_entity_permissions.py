"""Entity-scoped studio permissions for non-staff members."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from magicforms.entity_permissions import (
    MANAGE_FORMS,
    MANAGE_PEOPLE,
    VIEW_RESPONSES,
    read_or_write,
    user_has_entity_permission,
    user_has_any_entity_permission,
)
from magicforms.models import Entity, EntityMembership


class EntityPermissionsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.entity_a = Entity.objects.create(name="Org A", slug="org-a")
        self.entity_b = Entity.objects.create(name="Org B", slug="org-b")
        self.staff = User.objects.create_user(
            username="staff_a",
            password="x",
            is_staff=True,
        )
        self.member = User.objects.create_user(
            username="member_ab",
            password="x",
            is_staff=False,
        )
        EntityMembership.objects.create(user=self.staff, entity=self.entity_a)
        EntityMembership.objects.create(
            user=self.member,
            entity=self.entity_a,
            manage_forms_read=True,
            view_responses_read=True,
        )
        EntityMembership.objects.create(
            user=self.member,
            entity=self.entity_b,
            manage_people_write=True,
        )

    def test_staff_bypasses_flags(self):
        self.assertTrue(
            user_has_entity_permission(self.staff, self.entity_a.pk, MANAGE_PEOPLE)
        )
        self.assertTrue(
            user_has_entity_permission(self.staff, self.entity_b.pk, MANAGE_FORMS)
        )

    def test_read_write_per_entity(self):
        self.assertTrue(
            user_has_entity_permission(
                self.member, self.entity_a.pk, *read_or_write(MANAGE_FORMS)
            )
        )
        self.assertFalse(
            user_has_entity_permission(
                self.member,
                self.entity_a.pk,
                "manage_forms_write",
            )
        )
        self.assertTrue(
            user_has_entity_permission(
                self.member,
                self.entity_b.pk,
                "manage_people_write",
            )
        )

    def test_write_satisfies_read_check(self):
        self.assertTrue(
            user_has_entity_permission(
                self.member,
                self.entity_b.pk,
                "manage_people_read",
            )
        )

    def test_responses_grid_requires_view_responses_read(self):
        self.client.force_login(self.member)
        r = self.client.get(reverse("manage:responses_grid"))
        self.assertEqual(r.status_code, 200)
        EntityMembership.objects.filter(user=self.member, entity=self.entity_a).update(
            view_responses_read=False,
            view_responses_write=False,
        )
        r = self.client.get(reverse("manage:responses_grid"))
        self.assertEqual(r.status_code, 302)

    def test_people_list_with_read_or_write(self):
        self.client.force_login(self.member)
        r = self.client.get(reverse("manage:user_list"))
        self.assertEqual(r.status_code, 200)
        EntityMembership.objects.filter(user=self.member, entity=self.entity_b).update(
            manage_people_write=False,
            manage_people_read=False,
        )
        r = self.client.get(reverse("manage:user_list"))
        self.assertEqual(r.status_code, 302)

    def test_people_add_requires_write(self):
        self.client.force_login(self.member)
        EntityMembership.objects.filter(user=self.member, entity=self.entity_b).update(
            manage_people_write=False,
            manage_people_read=True,
        )
        r = self.client.get(reverse("manage:user_add"))
        self.assertEqual(r.status_code, 302)
