"""Process pending outbound POST delivery rows (run from cron every minute)."""

from django.core.management.base import BaseCommand

from magicforms.outbound.worker import process_pending_deliveries


class Command(BaseCommand):
    help = "Send pending form outbound POST deliveries to external endpoints."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum deliveries to process in one run (default 50).",
        )

    def handle(self, *args, **options):
        count = process_pending_deliveries(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Processed {count} outbound delivery(s)."))
