"""
Seed registrars and a set of IPOs so the app has data on first run.

    python manage.py seed_ipos
    python manage.py seed_ipos --flush    # wipe IPOs and registrars first

Why this exists: a reviewer who clones your repo should see a working app,
not an empty table. A seed command is also how you get realistic data into
a test database without committing a SQL dump.

update_or_create keyed on a natural key makes the command idempotent — run
it ten times, get the same rows.
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from ipos.models import IPO, Registrar

REGISTRARS = [
    ("MUFG Intime India", "mufg-intime",
     "https://linkintime.co.in/initial_offer/public-issues.html"),
    ("KFin Technologies", "kfintech",
     "https://kosmic.kfintech.com/ipostatus/"),
    ("Bigshare Services", "bigshare",
     "https://ipo.bigshareonline.com/ipo_status.html"),
    ("Maashitla Securities", "maashitla",
     "https://maashitla.com/allotment-status/public-issues"),
    ("Cameo Corporate Services", "cameo",
     "https://ipo.cameoindia.com/"),
    ("Skyline Financial Services", "skyline",
     "https://www.skylinerta.com/ipo.php"),
    ("Purva Sharegistry", "purva",
     "https://www.purvashare.com/investor-service/ipo-query"),
    ("Integrated Registry", "integrated",
     "https://ipo.integratedindia.in/"),
]

# Illustrative issues for a working demo. Replace with real ones you have
# applied to — the point is that the app opens with something in it.
IPOS = [
    dict(name="Meridian Speciality Chemicals", symbol="MERIDIAN", registrar="kfintech",
         board=IPO.Board.MAINBOARD, status=IPO.Status.LISTED,
         price_band_low="325", price_band_high="342", lot_size=43, issue_size_cr="1240.00",
         open_date=date(2026, 9, 15), close_date=date(2026, 9, 18),
         allotment_date=date(2026, 9, 21), refund_date=date(2026, 9, 22),
         listing_date=date(2026, 9, 24), listing_price="411.50", gmp="58"),

    dict(name="Kalyani Precision Tubes", symbol="KALYANITUBE", registrar="bigshare",
         board=IPO.Board.SME, status=IPO.Status.ALLOTTED,
         price_band_low="112", price_band_high="118", lot_size=1200, issue_size_cr="86.40",
         open_date=date(2026, 9, 23), close_date=date(2026, 9, 26),
         allotment_date=date(2026, 9, 30), refund_date=date(2026, 10, 1),
         listing_date=date(2026, 10, 5), gmp="22"),

    dict(name="Vaidya Diagnostics", symbol="VAIDYA", registrar="mufg-intime",
         board=IPO.Board.MAINBOARD, status=IPO.Status.OPEN,
         price_band_low="268", price_band_high="282", lot_size=53, issue_size_cr="2100.00",
         open_date=date(2026, 10, 1), close_date=date(2026, 10, 6),
         allotment_date=date(2026, 10, 9), refund_date=date(2026, 10, 10),
         listing_date=date(2026, 10, 13), gmp="31"),

    dict(name="Suryodaya Renewables", symbol="SURYODAYA", registrar="kfintech",
         board=IPO.Board.MAINBOARD, status=IPO.Status.UPCOMING,
         price_band_low="640", price_band_high="672", lot_size=22, issue_size_cr="3850.00",
         open_date=date(2026, 10, 14), close_date=date(2026, 10, 17),
         allotment_date=date(2026, 10, 20), refund_date=date(2026, 10, 21),
         listing_date=date(2026, 10, 23)),

    dict(name="Anantha Agritech", symbol="ANANTHA", registrar="maashitla",
         board=IPO.Board.SME, status=IPO.Status.LISTED,
         price_band_low="88", price_band_high="93", lot_size=1600, issue_size_cr="42.10",
         open_date=date(2026, 8, 19), close_date=date(2026, 8, 21),
         allotment_date=date(2026, 8, 25), refund_date=date(2026, 8, 26),
         listing_date=date(2026, 8, 28), listing_price="81.25", gmp="-6"),

    dict(name="Trident Logistics Park", symbol="TRIDENTLOG", registrar="cameo",
         board=IPO.Board.MAINBOARD, status=IPO.Status.LISTED,
         price_band_low="195", price_band_high="205", lot_size=73, issue_size_cr="980.00",
         open_date=date(2026, 7, 8), close_date=date(2026, 7, 10),
         allotment_date=date(2026, 7, 14), refund_date=date(2026, 7, 15),
         listing_date=date(2026, 7, 17), listing_price="248.00", gmp="44"),
]


class Command(BaseCommand):
    help = "Seed registrars and sample IPOs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing IPOs and registrars before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            count, _ = IPO.objects.all().delete()
            Registrar.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Flushed {count} IPO row(s)."))

        registrars = {}
        for name, slug, url in REGISTRARS:
            obj, created = Registrar.objects.update_or_create(
                slug=slug,
                defaults={"name": name, "status_check_url": url, "is_active": True},
            )
            registrars[slug] = obj
            self.stdout.write(f"  {'+' if created else '·'} {name}")

        for row in IPOS:
            data = dict(row)
            registrar = registrars[data.pop("registrar")]
            name = data.pop("name")

            # Strings → Decimal so the values land in the database with the
            # precision the column declares.
            for key in ("price_band_low", "price_band_high",
                        "issue_size_cr", "listing_price", "gmp"):
                if key in data and data[key] is not None:
                    data[key] = Decimal(data[key])

            obj, created = IPO.objects.update_or_create(
                name=name,
                defaults={"registrar": registrar, **data},
            )
            self.stdout.write(f"  {'+' if created else '·'} {obj.name}")

        self.stdout.write(self.style.SUCCESS(
            f"\nSeeded {Registrar.objects.count()} registrars "
            f"and {IPO.objects.count()} IPOs."
        ))