"""
Pull current, upcoming and recently closed IPOs from NSE.

    python manage.py sync_ipos
    python manage.py sync_ipos --past-days 120

Idempotent: safe to run as often as you like. Run it daily (Task Scheduler
or cron) together with check_allotments.
"""

from django.core.management.base import BaseCommand, CommandError

from ipos.sources.nse import NSEError
from ipos.sources.sync import sync_from_nse


class Command(BaseCommand):
    help = "Sync IPOs from NSE."

    def add_arguments(self, parser):
        parser.add_argument("--past-days", type=int, default=90,
                            help="Also import closed issues that opened within this many days (default 90).")

    def handle(self, *args, **options):
        try:
            report = sync_from_nse(past_days=options["past_days"])
        except NSEError as exc:
            raise CommandError(str(exc)) from exc

        for name in report.created:
            self.stdout.write(f"  + {name}")
        for name in report.updated:
            self.stdout.write(f"  ~ {name}")
        for err in report.errors:
            self.stdout.write(self.style.WARNING(f"  ! {err}"))
        self.stdout.write(self.style.SUCCESS(
            f"Created {len(report.created)}, updated {len(report.updated)}, "
            f"unchanged {report.unchanged}, errors {len(report.errors)}."
        ))
