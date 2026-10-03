"""
Bigshare Services — ipo.bigshareonline.com.

The issue list is plain <option> tags in ipo_status.html. The lookup is a
JSON POST to Data.aspx/FetchIpodetails returning Status = OK | NOTFOUND |
RATELIMIT | WARMING, with APPLIED / ALLOTED counts (or several Records when
one PAN has more than one application).
"""

from bs4 import BeautifulSoup

from .base import CheckResult, Outcome, RegistrarAdapter, RegistrarError, result_from_shares, to_int

BASE = "https://ipo.bigshareonline.com/"


def parse_companies(html: str) -> list[tuple[str, str]]:
    select = BeautifulSoup(html, "html.parser").find("select", id="ddlCompany")
    if select is None:
        return []
    return [(o["value"], o.get_text(strip=True)) for o in select.find_all("option") if o.get("value")]


def parse_result(d: dict) -> CheckResult:
    status = (d.get("Status") or "").upper()
    if status == "NOTFOUND":
        return CheckResult(Outcome.NOT_FOUND, message=d.get("Message") or "No record found.")
    if status in ("RATELIMIT", "WARMING"):
        return CheckResult(Outcome.ERROR, message=d.get("Message") or "Bigshare asked us to wait. Try again shortly.")
    if status not in ("", "OK"):
        return CheckResult(Outcome.ERROR, message=d.get("Message") or f"Bigshare returned {status}.")
    rows = d.get("Records") or [d]
    applied = sum(to_int(r.get("APPLIED")) for r in rows)
    allotted = sum(to_int(r.get("ALLOTED")) for r in rows)
    return result_from_shares(applied, allotted)


class BigshareAdapter(RegistrarAdapter):
    slug = "bigshare"

    def issues(self):
        res = self.http.get(BASE + "ipo_status.html")
        if res.status_code != 200:
            raise RegistrarError(f"Bigshare returned {res.status_code}.")
        return parse_companies(res.text)

    def check(self, issue_ref, pan):
        body = {"Applicationno": "", "Company": issue_ref, "SelectionType": "PN", "PanNo": pan,
                "txtcsdl": "", "txtDPID": "", "txtClId": "", "ddlType": "0", "lang": "en"}
        res = self.http.post(BASE + "Data.aspx/FetchIpodetails", json=body)
        if res.status_code in (429, 503):
            return CheckResult(Outcome.ERROR, message="Bigshare is rate-limiting requests. Try again in a minute.")
        if res.status_code != 200:
            raise RegistrarError(f"Bigshare returned {res.status_code}.")
        return parse_result(res.json().get("d") or {})
