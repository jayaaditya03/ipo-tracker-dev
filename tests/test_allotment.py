"""
Allotment adapters and the check service.

Registrar responses come from tests/fixtures/registrars/ — real captures for
issue lists and "not found" replies; success replies built in the exact shape
each registrar's own page reads (field names taken from their JS).
"""

import json
from pathlib import Path

import httpx
import pytest
import respx

from ipos.allotment import ADAPTERS, CheckResult, Outcome, RegistrarAdapter, bigshare, kfin, maashitla, mufg, skyline
from ipos.allotment.base import normalise_name
from ipos.allotment.service import check_applications
from ipos.models import Application, Registrar, StatusEvent

from .conftest import IPOFactory, RegistrarFactory, make_pan

FIX = Path(__file__).parent / "fixtures" / "registrars"


def read(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_normalise_name_matches_registrar_spellings():
    assert normalise_name("Shah Investor’s Home Limited - IPO") == normalise_name("Shah Investor's Home Limited")
    assert normalise_name("Anand Seamless Limited - SME IPO") == "ANAND SEAMLESS"


class TestMufg:
    def test_company_list(self):
        companies = mufg.parse_companies(read("mufg_getdetails.xml"))
        assert ("11961", "Shah Investor’s Home Limited - IPO") in companies

    def test_empty_dataset_is_not_found(self):
        assert mufg.parse_search("<NewDataSet />").outcome == Outcome.NOT_FOUND

    def test_allotted(self):
        xml = "<NewDataSet><Table><NAME1>X</NAME1><SHARES>136</SHARES><ALLOT>68</ALLOT></Table></NewDataSet>"
        r = mufg.parse_search(xml)
        assert (r.outcome, r.shares_applied, r.shares_allotted) == (Outcome.ALLOTTED, 136, 68)

    def test_not_allotted(self):
        xml = "<NewDataSet><Table><SHARES>68</SHARES><ALLOT>0</ALLOT></Table></NewDataSet>"
        assert mufg.parse_search(xml).outcome == Outcome.NOT_ALLOTTED

    def test_message_table_is_error(self):
        xml = "<NewDataSet><Table1><Msg>Invalid token</Msg></Table1></NewDataSet>"
        assert mufg.parse_search(xml).outcome == Outcome.ERROR

    def test_token_encryption_matches_cryptojs(self):
        # Expected value from Node's crypto (aes-128-cbc, same key/IV), which
        # is what CryptoJS produces in the browser.
        assert mufg.encrypt_token("117138884") == "DrMQLqz0FounrUUq5LaONQ=="

    @respx.mock
    def test_full_flow(self):
        respx.get(mufg.BASE + "public-issues.html").respond(200, text="ok")
        respx.post(mufg.BASE + "IPO.aspx/GetDetails").respond(200, json={"d": read("mufg_getdetails.xml")})
        respx.post(mufg.BASE + "IPO.aspx/generateToken").respond(200, json={"d": "117138884"})
        search = respx.post(mufg.BASE + "IPO.aspx/SearchOnPan").respond(
            200, json={"d": "<NewDataSet><Table><SHARES>85</SHARES><ALLOT>85</ALLOT></Table></NewDataSet>"})
        a = mufg.MufgIntimeAdapter()
        ref = a.find_issue("Shah Investor's Home Limited")
        assert ref == "11961"
        assert a.check(ref, "ABCDE1234F").shares_allotted == 85
        assert "'clientid': '11961'" in search.calls.last.request.content.decode()


class TestBigshare:
    def test_company_list_ignores_commented_options(self):
        companies = bigshare.parse_companies(read("bigshare_page.html"))
        assert ("9051", "ADROIT INDUSTRIES INDIA LTD") in companies
        assert all(ref != "9049" for ref, _ in companies)        # commented out on the page

    def test_not_found(self):
        d = json.loads(read("bigshare_notfound.json"))["d"]
        assert bigshare.parse_result(d).outcome == Outcome.NOT_FOUND

    def test_allotted_and_rate_limit(self):
        assert bigshare.parse_result({"Status": "OK", "APPLIED": "1,200", "ALLOTED": "1,200"}).shares_allotted == 1200
        assert bigshare.parse_result({"Status": "OK", "APPLIED": "200", "ALLOTED": "0"}).outcome == Outcome.NOT_ALLOTTED
        assert bigshare.parse_result({"Status": "RATELIMIT", "Message": "wait"}).outcome == Outcome.ERROR

    def test_multiple_records_are_summed(self):
        d = {"Status": "OK", "MatchCount": 2,
             "Records": [{"APPLIED": "200", "ALLOTED": "200"}, {"APPLIED": "200", "ALLOTED": "0"}]}
        r = bigshare.parse_result(d)
        assert (r.shares_applied, r.shares_allotted) == (400, 200)


class TestKfin:
    def test_bundle_list(self):
        assert kfin.parse_bundle(read("kfin_bundle_excerpt.js")) == [("37168935020", "SRIT INDIA LIMITED")]

    @respx.mock
    def test_full_flow(self):
        respx.get(kfin.SITE).respond(200, text='<script defer src="./static/js/main.abc123.js"></script>')
        respx.get(kfin.SITE + "static/js/main.abc123.js").respond(200, text=read("kfin_bundle_excerpt.js"))
        api = respx.get(kfin.API).mock(side_effect=lambda req: (
            httpx.Response(200, json={"data": [{"App_Shares": "115", "All_Shares": "115", "Pan_No": "x"}]})
            if req.headers["reqparam"] == "ABCDE1234F" else httpx.Response(404, json={"error": "Record Not Found"})
        ))
        a = kfin.KfinAdapter()
        ref = a.find_issue("Srit India Limited")
        assert a.check(ref, "ABCDE1234F").outcome == Outcome.ALLOTTED
        assert a.check(ref, "PQRST6789Z").outcome == Outcome.NOT_FOUND
        assert api.calls.last.request.headers["client_id"] == "37168935020"


# ------------------------------------------------------------- service


class FakeAdapter(RegistrarAdapter):
    """Answers from a dict keyed by PAN, so service tests need no HTTP."""
    slug = "fake"
    answers: dict = {}

    def __init__(self, http=None):
        pass

    def issues(self):
        return [("REF1", "Fake Issue Limited")]

    def check(self, issue_ref, pan):
        assert issue_ref == "REF1"
        return self.answers[pan]


@pytest.fixture
def fake_registrar(db):
    return RegistrarFactory(name="Fake", slug="fake")


@pytest.mark.django_db
class TestService:
    def _apps(self, user, registrar):
        ipo = IPOFactory(name="Fake Issue Limited", registrar=registrar)
        a = Application.objects.create(owner=user, ipo=ipo, pan=make_pan(user, "ABCDE1234F", "Self"),
                                       bid_price=100, lots=2, status=Application.Status.APPLIED)
        b = Application.objects.create(owner=user, ipo=ipo, pan=make_pan(user, "PQRST6789Z", "Mother"),
                                       bid_price=100, status=Application.Status.APPLIED)
        return ipo, a, b

    def test_records_results_as_registrar_events(self, user, fake_registrar):
        ipo, a, b = self._apps(user, fake_registrar)
        FakeAdapter.answers = {
            "ABCDE1234F": CheckResult(Outcome.ALLOTTED, 300, 150),
            "PQRST6789Z": CheckResult(Outcome.NOT_ALLOTTED, 150, 0),
        }
        rows = check_applications([a, b], adapters={"fake": FakeAdapter}, pause=0)

        a.refresh_from_db()
        b.refresh_from_db()
        ipo.refresh_from_db()
        assert a.status == Application.Status.PARTIAL and a.shares_allotted == 150
        assert b.status == Application.Status.REJECTED
        assert ipo.registrar_ref == "REF1"                                  # cached
        assert a.events.first().source == StatusEvent.Source.REGISTRAR
        assert [r["outcome"] for r in rows] == ["allotted", "not_allotted"]
        assert all("ABCDE" not in json.dumps(r, default=str) for r in rows)  # never echo the PAN

    def test_error_on_one_pan_does_not_stop_batch(self, user, fake_registrar):
        _, a, b = self._apps(user, fake_registrar)

        class Flaky(FakeAdapter):
            def check(self, issue_ref, pan):
                if pan == "ABCDE1234F":
                    raise httpx.ConnectError("boom")
                return CheckResult(Outcome.ALLOTTED, 150, 150)

        rows = check_applications([a, b], adapters={"fake": Flaky}, pause=0)
        assert [r["outcome"] for r in rows] == ["error", "allotted"]
        a.refresh_from_db()
        assert a.status == Application.Status.APPLIED

    def test_unsupported_registrar(self, user):
        reg = Registrar.objects.create(name="Purva Sharegistry", slug="purva", status_check_url="https://x.test")
        ipo = IPOFactory(registrar=reg)
        app = Application.objects.create(owner=user, ipo=ipo, pan=make_pan(user), bid_price=100,
                                         status=Application.Status.APPLIED)
        [row] = check_applications([app], adapters={}, pause=0)
        assert row["outcome"] == "unsupported"
        assert row["status_check_url"] == "https://x.test"

    def test_issue_not_listed_yet(self, user, fake_registrar):
        ipo = IPOFactory(name="Something Else Limited", registrar=fake_registrar)
        app = Application.objects.create(owner=user, ipo=ipo, pan=make_pan(user), bid_price=100,
                                         status=Application.Status.APPLIED)
        [row] = check_applications([app], adapters={"fake": FakeAdapter}, pause=0)
        assert row["outcome"] == "not_published"


@pytest.mark.django_db
def test_check_endpoint_only_touches_own_applications(client, user, other_user, fake_registrar, monkeypatch):
    monkeypatch.setitem(ADAPTERS, "fake", FakeAdapter)
    monkeypatch.setattr("ipos.allotment.service.time.sleep", lambda s: None)
    FakeAdapter.answers = {"ABCDE1234F": CheckResult(Outcome.ALLOTTED, 150, 150)}
    ipo = IPOFactory(name="Fake Issue Limited", registrar=fake_registrar)
    mine = Application.objects.create(owner=user, ipo=ipo, pan=make_pan(user), bid_price=100,
                                      status=Application.Status.APPLIED)
    Application.objects.create(owner=other_user, ipo=ipo, pan=make_pan(other_user, "ZZZZZ9999Z"),
                               bid_price=100, status=Application.Status.APPLIED)

    res = client.post("/api/applications/check/", {"ipo_id": ipo.id}, format="json")
    assert res.status_code == 200
    assert [r["application_id"] for r in res.data["results"]] == [mine.id]
    assert res.data["summary"] == {"allotted": 1}


@pytest.mark.django_db
class TestCheckPans:
    """Checking any issue — including listed ones — without leaving fake applications behind."""

    @pytest.fixture(autouse=True)
    def _fake(self, monkeypatch, fake_registrar):
        monkeypatch.setitem(ADAPTERS, "fake", FakeAdapter)
        monkeypatch.setattr("ipos.allotment.service.time.sleep", lambda s: None)
        self.ipo = IPOFactory(name="Fake Issue Limited", registrar=fake_registrar,
                              status="LISTED", lot_size=150)

    def test_keeps_confirmed_drops_unknown(self, client, user):
        got = make_pan(user, "ABCDE1234F", "Self")
        missed = make_pan(user, "PQRST6789Z", "Mother")
        never = make_pan(user, "LMNOP4321Q", "Father")
        FakeAdapter.answers = {
            "ABCDE1234F": CheckResult(Outcome.ALLOTTED, 300, 150),
            "PQRST6789Z": CheckResult(Outcome.NOT_ALLOTTED, 150, 0),
            "LMNOP4321Q": CheckResult(Outcome.NOT_FOUND),
        }
        res = client.post("/api/applications/check_pans/",
                          {"ipo_id": self.ipo.id, "pan_ids": [got.id, missed.id, never.id]}, format="json")
        assert res.status_code == 200, res.data
        apps = {a.pan_id: a for a in Application.objects.filter(ipo=self.ipo)}
        assert set(apps) == {got.id, missed.id}                     # Father's record removed
        assert apps[got.id].status == Application.Status.PARTIAL
        assert apps[got.id].lots == 2                               # corrected from 300 shares applied
        assert apps[missed.id].status == Application.Status.REJECTED
        assert {r["pan_label"]: r["kept"] for r in res.data["results"]} == \
            {"Self": True, "Mother": True, "Father": False}

    def test_never_deletes_an_existing_application(self, client, user):
        pan = make_pan(user)
        app = Application.objects.create(owner=user, ipo=self.ipo, pan=pan, bid_price=100,
                                         status=Application.Status.APPLIED)
        FakeAdapter.answers = {"ABCDE1234F": CheckResult(Outcome.NOT_FOUND)}
        client.post("/api/applications/check_pans/", {"ipo_id": self.ipo.id, "pan_ids": [pan.id]}, format="json")
        assert Application.objects.filter(id=app.id).exists()

    def test_rejects_other_users_pan(self, client, other_user):
        theirs = make_pan(other_user)
        res = client.post("/api/applications/check_pans/",
                          {"ipo_id": self.ipo.id, "pan_ids": [theirs.id]}, format="json")
        assert res.status_code == 400
        assert not Application.objects.exists()


class TestMaashitla:
    def test_directory(self):
        companies = maashitla.parse_directory(json.loads(read("maashitla_directory.json")))
        assert ("himalayan-solar-limited", "HIMALAYAN SOLAR LIMITED") in companies

    def test_empty_reply_is_not_found(self):
        # What the live API returned for a PAN with no application.
        assert maashitla.parse_check({}).outcome == Outcome.NOT_FOUND

    def test_allotted_and_not(self):
        r = maashitla.parse_check({"name": "X", "shares_applied": "1200", "shares_allotted": "1200"})
        assert (r.outcome, r.shares_allotted) == (Outcome.ALLOTTED, 1200)
        r = maashitla.parse_check({"name": "X", "shares_applied": "1200", "shares_allotted": "0"})
        assert r.outcome == Outcome.NOT_ALLOTTED

    @respx.mock
    def test_full_flow(self):
        respx.get(maashitla.DIRECTORY).respond(200, text=read("maashitla_directory.json"))
        api = respx.get(url__startswith=maashitla.CHECK).respond(404)
        a = maashitla.MaashitlaAdapter()
        ref = a.find_issue("Himalayan Solar Limited")
        assert ref == "himalayan-solar-limited"
        assert a.check(ref, "ABCDE1234F").outcome == Outcome.NOT_FOUND
        assert api.calls.last.request.url.path.endswith("/check/himalayan-solar-limited")


class TestSkyline:
    def test_companies_and_token(self):
        companies = skyline.parse_companies(read("skyline_companies.html"))
        assert ("3510", "MADHUR KNIT CRAFTS LIMITED") in companies
        assert len(skyline.csrf_token(read("skyline_form.html"))) == 64

    def test_no_record(self):
        assert skyline.parse_result(read("skyline_notfound.html")).outcome == Outcome.NOT_FOUND

    def test_result_table(self):
        html = ("<table><tr><td>Name</td><td>X</td></tr>"
                "<tr><td>Shares Applied</td><td>2,000</td></tr><tr><td>Shares Allotted</td><td>1,000</td></tr></table>")
        r = skyline.parse_result(html)
        assert (r.outcome, r.shares_applied, r.shares_allotted) == (Outcome.ALLOTTED, 2000, 1000)

    def test_unreadable_reply_is_an_error(self):
        with pytest.raises(skyline.RegistrarError):
            skyline.parse_result("<p>Something unexpected</p>")

    @respx.mock
    def test_full_flow(self):
        respx.get(skyline.BASE + "ipo.php").respond(200, text=read("skyline_companies.html"))
        post = respx.post(skyline.BASE + "display_application.php").mock(side_effect=[
            httpx.Response(200, text=read("skyline_form.html")),
            httpx.Response(200, text=read("skyline_notfound.html")),
        ])
        a = skyline.SkylineAdapter()
        ref = a.find_issue("Madhur Knit Crafts Limited")
        assert a.check(ref, "ABCDE1234F").outcome == Outcome.NOT_FOUND
        sent = post.calls.last.request.content.decode()
        assert "pan=ABCDE1234F" in sent and "csrf_token=" in sent and "company=3510" in sent
