"""
Move every IPO's stored status forward to what today's date implies.

    python manage.py refresh_ipo_status

Run it daily (cron / Task Scheduler) so "Open" and "Allotment out" stay
accurate without anyone touching the admin. Same logic as the admin action.
"""

from django.core.management.base import BaseCommand

from ipos.models import IPO


class Command(BaseCommand):
    help = "Recalculate IPO status from the current date."

    def handle(self, *args, **options):
        updated = 0
        for ipo in IPO.objects.exclude(status=IPO.Status.WITHDRAWN):
            new = ipo.derive_status()
            if new != ipo.status:
                self.stdout.write(f"  {ipo.name}: {ipo.status} → {new}")
                ipo.status = new
                ipo.save(update_fields=["status", "updated_at"])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} issue(s)."))
