from django.core.management.base import BaseCommand

from magicforms.sample_forms_library import load_sample_forms_live


class Command(BaseCommand):
    help = (
        "For every organization, ensure draft sample forms exist across HR, Finance, Operations, "
        "Education, Government, Surveys, IT, Medical, and Business correspondence (categories + fields + one workflow step). "
        "Safe to run repeatedly; only missing forms are added. Staff claim templates from the dashboard."
    )

    def handle(self, *args, **options):
        entity_count, created = load_sample_forms_live()
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {entity_count} organization(s); created {created} new sample form(s) in total."
            )
        )
