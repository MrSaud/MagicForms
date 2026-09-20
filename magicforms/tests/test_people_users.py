from django.contrib.auth import get_user_model
from django.test import TestCase

from magicforms.entity_access import users_visible_in_people
from magicforms.models import Entity, EntityMembership

User = get_user_model()


class UsersVisibleInPeopleTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Acme", slug="acme")
        self.staff = User.objects.create_user(
            username="orgadmin",
            password="x",
            is_staff=True,
        )
        self.end_user = User.objects.create_user(
            username="applicant",
            password="x",
            is_staff=False,
        )
        EntityMembership.objects.create(user=self.staff, entity=self.entity)
        EntityMembership.objects.create(user=self.end_user, entity=self.entity)

    def test_org_staff_sees_staff_and_end_users(self):
        pks = set(users_visible_in_people(self.staff).values_list("pk", flat=True))
        self.assertIn(self.staff.pk, pks)
        self.assertIn(self.end_user.pk, pks)

    def test_end_user_not_listed_without_membership(self):
        outsider = User.objects.create_user(username="outsider", password="x")
        pks = set(users_visible_in_people(self.staff).values_list("pk", flat=True))
        self.assertNotIn(outsider.pk, pks)
