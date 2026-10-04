"""
Skyline Financial Services — skylinerta.com.

Plain PHP forms, two steps:
  1. ipo.php lists issues as <option>s in #company.
  2. POST display_application.php with company=<id> returns the search form
     with a csrf_token; POSTing that back with pan=... returns the result.

"No record found" in the reply means no application. Otherwise the result
is read from its table by label ("applied" / "allot"), since Skyline does
not expose a JSON API.
"""

import re

from bs4 import BeautifulSoup

from .base import CheckResult, Outcome, RegistrarAdapter, RegistrarError, result_from_shares, to_int

BASE = "https://www.skylinerta.com/"


def parse_companies(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    return [(o["value"], " ".join(o.get_text().split()))
            for o in soup.select("select#company option") if o.get("value")]


def csrf_token(html: str) -> str:
    field = BeautifulSoup(html, "html.parser").find("input", {"name": "csrf_token"})
    if not field or not field.get("value"):
        raise RegistrarError("Skyline's search form has changed — no CSRF token found.")
    return field["value"]


def parse_result(html: str) -> CheckResult:
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text(" ").split()).lower()
    if "no record found" in text:
        return CheckResult(Outcome.NOT_FOUND, message="No application found for this PAN.")

    # Collect label → value pairs from the result table(s).
    pairs: dict[str, str] = {}
    for row in soup.find_all("tr"):
        cells = [" ".join(c.get_text(" ").split()) for c in row.find_all(["th", "td"])]
        for label, value in zip(cells[::2], cells[1::2], strict=False):
            pairs[label.lower()] = value
    applied = next((v for k, v in pairs.items() if "applied" in k), None)
    allotted = next((v for k, v in pairs.items() if re.search(r"allot", k) and "applied" not in k), None)
    if applied is None or allotted is None:
        raise RegistrarError("Couldn't read Skyline's reply — the page layout may have changed.")
    return result_from_shares(to_int(applied), to_int(allotted))


class SkylineAdapter(RegistrarAdapter):
    slug = "skyline"

    def issues(self):
        res = self.http.get(BASE + "ipo.php")
        if res.status_code != 200:
            raise RegistrarError(f"Skyline returned {res.status_code}.")
        return parse_companies(res.text)

    def check(self, issue_ref, pan):
        form = self.http.post(BASE + "display_application.php", data={"company": issue_ref})
        if form.status_code != 200:
            raise RegistrarError(f"Skyline returned {form.status_code}.")
        res = self.http.post(BASE + "display_application.php", data={
            "client_id": "", "application_no": "", "pan": pan,
            "csrf_token": csrf_token(form.text), "company": issue_ref, "action": "search",
        })
        if res.status_code != 200:
            raise RegistrarError(f"Skyline returned {res.status_code}.")
        return parse_result(res.text)
