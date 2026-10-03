"""
Check allotment for every pending application whose allotment date has arrived.

    python manage.py check_allotments

Run it a few times on allotment days (Task Scheduler / cron), after
sync_ipos. Applications already resolved are skipped.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from ipos.allotment.service import CHECKABLE, check_applications
from ipos.models import Application


class Command(BaseCommand):
    help = "Ask registrars for allotment results of pending applications."

    def handle(self, *args, **options):
        today = timezone.localdate()
        apps = (Application.objects
                .filter(status__in=CHECKABLE)
                .filter(Q(ipo__allotment_date__isnull=True) | Q(ipo__allotment_date__lte=today))
                .select_related("ipo", "ipo__registrar", "pan")
                .order_by("ipo_id", "id"))

        rows = check_applications(apps)
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
            self.stdout.write(f"  {r['ipo_name']} / {r['pan_label']}: {r['outcome']} {r.get('message', '')}".rstrip())
        summary = ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "nothing to check"
        self.stdout.write(self.style.SUCCESS(f"Checked {len(rows)} application(s): {summary}."))
