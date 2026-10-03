import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from ipos.models import IPO
from ipos.sources.nse import BASE, NSEClient, parse_detail, parse_price_range
from ipos.sources.registrars import resolve_registrar
from ipos.sources.sync import add_working_days, sync_from_nse

from .conftest import IPOFactory

FIX = Path(__file__).parent / "fixtures" / "nse"
TODAY = date(2026, 10, 3)   # the day the fixtures were recorded


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def nse():
    """Mocks every NSE endpoint with the recorded responses."""
    def detail(request):
        sym = request.url.params["symbol"]
        path = FIX / f"detail_{sym}.json"
        return httpx.Response(200, json=load(path.name)) if path.exists() else httpx.Response(404)

    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__startswith=f"{BASE}/market-data/").respond(200, text="<html></html>")
        mock.get(f"{BASE}/api/all-upcoming-issues").respond(200, json=load("upcoming.json"))
        mock.get(f"{BASE}/api/public-past-issues").respond(200, json=load("past.json"))
        mock.get(f"{BASE}/api/ipo-detail").mock(side_effect=detail)
        yield NSEClient(retries=1, pause=0)


class TestParsing:
    @pytest.mark.parametrize("text,expected", [
        ("Rs.208 to Rs.220", (Decimal(208), Decimal(220))),
        ("Rs. 70/- to Rs. 75/-per equity share ", (Decimal(70), Decimal(75))),
        ("Rs.1000", (Decimal(1000), Decimal(1000))),
        ("-", (None, None)),
    ])
    def test_price_range(self, text, expected):
        assert parse_price_range(text) == expected

    def test_detail_mainboard_uses_bid_lot(self):
        d = parse_detail(load("detail_SRIT.json"))
        assert d["lot_size"] == 115
        assert d["registrar_name"].startswith("KFin")

    def test_detail_sme_uses_lot_size(self):
        d = parse_detail(load("detail_HIMALAYAN.json"))
        assert d["lot_size"] == 1200
        assert d["registrar_name"].startswith("Maashitla")

    def test_working_days_skip_weekend(self):
        assert add_working_days(date(2026, 10, 2), 1) == date(2026, 10, 5)   # Fri → Mon


@pytest.mark.django_db
class TestRegistrarResolution:
    def test_aliases(self):
        assert resolve_registrar("MUFG Intime India Private Limited ").slug == "mufg-intime"
        assert resolve_registrar("Link Intime India Pvt Ltd").slug == "mufg-intime"
        assert resolve_registrar("Cameo Corporate Service Limited").slug == "cameo"

    def test_unknown_name_creates_registrar(self):
        r = resolve_registrar("Acme Registry Private Limited")
        assert r.slug == "acme-registry"

    def test_blank_is_unknown(self):
        assert resolve_registrar(None).slug == "unknown"


@pytest.mark.django_db
class TestSync:
    def test_imports_equity_issues_only(self, nse):
        report = sync_from_nse(nse, today=TODAY, detail_pause=0)
        symbols = set(IPO.objects.values_list("symbol", flat=True))
        assert {"VNL", "NITYAS", "RKFAL", "SRIT", "HIMALAYAN", "AONESTEELS"} <= symbols
        assert "SMCG04" not in symbols              # debt issue
        assert not report.errors

    def test_fields_from_list_and_detail(self, nse):
        sync_from_nse(nse, today=TODAY, detail_pause=0)
        sme = IPO.objects.get(symbol="HIMALAYAN")
        assert sme.board == IPO.Board.SME
        assert sme.lot_size == 1200
        assert sme.registrar.slug == "maashitla"
        assert sme.price_band_high == Decimal("103")
        assert sme.source == IPO.Source.NSE

        nityas = IPO.objects.get(symbol="NITYAS")
        assert nityas.status == IPO.Status.OPEN
        assert nityas.registrar.slug == "bigshare"
        assert nityas.allotment_date == date(2026, 10, 6)   # close Mon 5th → Tue 6th
        assert nityas.dates_estimated

    def test_listed_issue_keeps_published_listing_date(self, nse):
        sync_from_nse(nse, today=TODAY, detail_pause=0)
        a = IPO.objects.get(symbol="AONESTEELS")
        assert a.listing_date == date(2026, 10, 1)
        assert a.status == IPO.Status.LISTED
        assert not a.dates_estimated

    def test_idempotent(self, nse):
        sync_from_nse(nse, today=TODAY, detail_pause=0)
        count = IPO.objects.count()
        report = sync_from_nse(nse, today=TODAY, detail_pause=0)
        assert IPO.objects.count() == count
        assert not report.created

    def test_does_not_wipe_hand_entered_listing_price(self, nse):
        sync_from_nse(nse, today=TODAY, detail_pause=0)
        IPO.objects.filter(symbol="AONESTEELS").update(listing_price=Decimal("450"))
        sync_from_nse(nse, today=TODAY, detail_pause=0)
        assert IPO.objects.get(symbol="AONESTEELS").listing_price == Decimal("450")

    def test_matches_hand_entered_issue_by_name(self, nse):
        manual = IPOFactory(name="Srit India Limited", symbol="", lot_size=None)
        sync_from_nse(nse, today=TODAY, detail_pause=0)
        manual.refresh_from_db()
        assert manual.symbol == "SRIT"
        assert manual.lot_size == 115

    def test_sync_endpoint_is_staff_only(self, client):
        assert client.post("/api/ipos/sync/").status_code == 403
