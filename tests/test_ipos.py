from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from ipos.models import IPO, Application

from .conftest import IPOFactory, make_pan

pytestmark = pytest.mark.django_db


class TestIPOCatalogue:
    def test_list_and_detail(self, client, ipo):
        res = client.get("/api/ipos/")
        assert res.data["count"] == 1
        assert res.data["results"][0]["lot_amount"] == "15000.00"

        res = client.get(f"/api/ipos/{ipo.pk}/")
        assert res.data["my_application_count"] == 0

    def test_open_now(self, client, ipo):
        today = timezone.localdate()
        IPOFactory(open_date=today + timedelta(days=5), close_date=today + timedelta(days=8))
        res = client.get("/api/ipos/open_now/")
        assert [r["id"] for r in res.data] == [ipo.pk]

    def test_read_only(self, client, ipo):
        assert client.delete(f"/api/ipos/{ipo.pk}/").status_code == 405

    def test_derive_status(self):
        today = timezone.localdate()
        ipo = IPO(open_date=today - timedelta(days=10), close_date=today - timedelta(days=7),
                  allotment_date=today - timedelta(days=5), listing_date=today + timedelta(days=1))
        assert ipo.derive_status() == IPO.Status.ALLOTTED


class TestApplications:
    def test_create_defaults_bid_to_cutoff(self, client, user, ipo):
        pan = make_pan(user)
        res = client.post("/api/applications/", {"ipo_id": ipo.pk, "pan_id": pan.pk, "lots": 2})
        assert res.status_code == 201, res.data
        assert res.data["bid_price"] == "100.00"
        assert res.data["amount_blocked"] == "30000.00"

    def test_cannot_apply_with_someone_elses_pan(self, client, other_user, ipo):
        theirs = make_pan(other_user)
        res = client.post("/api/applications/", {"ipo_id": ipo.pk, "pan_id": theirs.pk})
        assert res.status_code == 400
        assert "pan_id" in res.data

    def test_retail_limit(self, client, user, ipo):
        pan = make_pan(user)
        res = client.post("/api/applications/", {"ipo_id": ipo.pk, "pan_id": pan.pk, "lots": 14})
        assert res.status_code == 400
        assert "lots" in res.data

    def test_bulk_apply_skips_duplicates(self, client, user, ipo):
        a = make_pan(user, "ABCDE1234F", "Self")
        b = make_pan(user, "PQRST6789Z", "Father")
        Application.objects.create(owner=user, ipo=ipo, pan=a, bid_price=100)

        res = client.post("/api/applications/bulk/",
                          {"ipo_id": ipo.pk, "pan_ids": [a.pk, b.pk]}, format="json")
        assert res.status_code == 201
        assert res.data["summary"] == {"requested": 2, "created": 1, "skipped": 1}
        assert res.data["skipped"][0]["pan_id"] == a.pk

    def test_bulk_apply_enforces_retail_limit(self, client, user, ipo):
        pan = make_pan(user)
        res = client.post("/api/applications/bulk/",
                          {"ipo_id": ipo.pk, "pan_ids": [pan.pk], "lots": 14}, format="json")
        assert res.status_code == 400
        assert "lots" in res.data
        assert not Application.objects.exists()

    def test_set_status_logs_event(self, client, user, ipo):
        pan = make_pan(user)
        app = Application.objects.create(owner=user, ipo=ipo, pan=pan, bid_price=100,
                                         status=Application.Status.APPLIED)
        res = client.post(f"/api/applications/{app.pk}/set_status/", {"status": "ALLOTTED"})
        assert res.status_code == 200
        assert res.data["shares_allotted"] == 150

        events = client.get(f"/api/applications/{app.pk}/events/").data
        assert events[0]["from_status"] == "APPLIED"
        assert events[0]["to_status"] == "ALLOTTED"

    def test_set_status_rejects_too_many_shares(self, client, user, ipo):
        pan = make_pan(user)
        app = Application.objects.create(owner=user, ipo=ipo, pan=pan, bid_price=100)
        res = client.post(f"/api/applications/{app.pk}/set_status/",
                          {"status": "PARTIAL", "shares_allotted": 999})
        assert res.status_code == 400

    def test_other_users_applications_hidden(self, client, other_user, ipo):
        pan = make_pan(other_user)
        app = Application.objects.create(owner=other_user, ipo=ipo, pan=pan, bid_price=100)
        assert client.get("/api/applications/").data["count"] == 0
        assert client.get(f"/api/applications/{app.pk}/").status_code == 404


def test_dashboard_summary(client, user, ipo):
    ipo.listing_price = Decimal("120")
    ipo.save()
    a = make_pan(user, "ABCDE1234F", "Self")
    b = make_pan(user, "PQRST6789Z", "Father")
    Application.objects.create(owner=user, ipo=ipo, pan=a, bid_price=100,
                               status=Application.Status.ALLOTTED, shares_allotted=150)
    Application.objects.create(owner=user, ipo=ipo, pan=b, bid_price=100,
                               status=Application.Status.REJECTED)

    data = client.get("/api/dashboard/summary/").data
    assert data["applications"] == 2
    assert data["allotted"] == 1
    assert data["hit_rate"] == 50.0
    assert data["invested"] == Decimal("15000")
    assert data["realised_gain"] == Decimal("3000")


def test_applications_filter_by_status_group(client, user, ipo):
    a = make_pan(user, "ABCDE1234F", "Self")
    b = make_pan(user, "PQRST6789Z", "Father")
    c = make_pan(user, "LMNOP4321Q", "Mother")
    Application.objects.create(owner=user, ipo=ipo, pan=a, bid_price=100, status=Application.Status.ALLOTTED)
    Application.objects.create(owner=user, ipo=ipo, pan=b, bid_price=100, status=Application.Status.PARTIAL)
    Application.objects.create(owner=user, ipo=ipo, pan=c, bid_price=100, status=Application.Status.REJECTED)
    res = client.get("/api/applications/", {"status__in": "ALLOTTED,PARTIAL"})
    assert {r["pan_label"] for r in res.data["results"]} == {"Self", "Father"}
    res = client.get("/api/applications/", {"pan": c.id})
    assert [r["pan_label"] for r in res.data["results"]] == ["Mother"]
