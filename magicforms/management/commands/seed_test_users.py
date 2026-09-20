"""
Create staff test users (emp1 … empN) and attach them to the default organization.

The default entity is the one with slug ``default`` (created by migration 0018).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from magicforms.models import Entity, EntityMembership


class Command(BaseCommand):
    help = "Create emp1..empN staff users with membership on the default entity (slug=default)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=100,
            help="Number of users to create (default: 100).",
        )
        parser.add_argument(
            "--prefix",
            type=str,
            default="emp",
            help="Username prefix (default: emp → emp1, emp2, …).",
        )
        parser.add_argument(
            "--entity-slug",
            type=str,
            default="default",
            help="Organization slug (default: default).",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="TestPass123!",
            help="Password for new users (default: TestPass123!).",
        )
        parser.add_argument(
            "--email-domain",
            type=str,
            default="example.invalid",
            help="Email host for generated addresses (default: example.invalid).",
        )

    def handle(self, *args, **options):
        count = options["count"]
        prefix = options["prefix"]
        slug = options["entity_slug"]
        password = options["password"]
        email_domain = options["email_domain"]

        if count < 1 or count > 10_000:
            raise CommandError("--count must be between 1 and 10000.")

        try:
            entity = Entity.objects.get(slug=slug, is_active=True)
        except Entity.DoesNotExist as exc:
            raise CommandError(
                f'No active entity with slug "{slug}". Create one in the studio (superuser) first.'
            ) from exc

        User = get_user_model()
        created = 0
        linked = 0
        skipped = 0

        with transaction.atomic():
            for i in range(1, count + 1):
                username = f"{prefix}{i}"
                if User.objects.filter(username=username).exists():
                    user = User.objects.get(username=username)
                    skipped += 1
                    newly_created = False
                else:
                    user = User(
                        username=username,
                        email=f"{username}@{email_domain}",
                        is_staff=True,
                        is_active=True,
                    )
                    user.set_password(password)
                    user.save()
                    created += 1
                    newly_created = True

                _, was_new = EntityMembership.objects.get_or_create(
                    user=user,
                    entity=entity,
                )
                if was_new:
                    linked += 1

                if newly_created and hasattr(user, "profile"):
                    prof = user.profile
                    if not prof.employee_number:
                        prof.employee_number = username
                        prof.save(update_fields=["employee_number"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Entity: {entity.name} (slug={entity.slug}). "
                f"Created users: {created}, already existed: {skipped}, "
                f"new memberships: {linked}."
            )
        )
