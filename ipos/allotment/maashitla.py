"""
Maashitla Securities — maashitla.com.

A React site. Its public-issues page lists issues from
api.maashitla.com/api/company-directory and looks a PAN up at an AWS
endpoint: GET .../prod/check/{company_slug}?pan=... — 404 or an empty /
nameless object means no record; otherwise {name, shares_applied,
shares_allotted}.
"""

from .base import CheckResult, Outcome, RegistrarAdapter, RegistrarError, result_from_shares, to_int

DIRECTORY = "https://api.maashitla.com/api/company-directory"
CHECK = "https://pnjbvxj6md.execute-api.ap-south-1.amazonaws.com/prod/check/"
SITE = "https://maashitla.com"


def parse_directory(payload: dict) -> list[tuple[str, str]]:
    return [(c["company_slug"], c["company_name"]) for c in payload.get("companies", []) if c.get("company_slug")]


def parse_check(payload: dict | None) -> CheckResult:
    # Same rule as Maashitla's own page: no name means no record.
    if not payload or payload.get("name") is None:
        return CheckResult(Outcome.NOT_FOUND, message="No application found for this PAN.")
    return result_from_shares(to_int(payload.get("shares_applied")), to_int(payload.get("shares_allotted")))


class MaashitlaAdapter(RegistrarAdapter):
    slug = "maashitla"

    def issues(self):
        res = self.http.get(DIRECTORY, headers={"Origin": SITE})
        if res.status_code != 200:
            raise RegistrarError(f"Maashitla returned {res.status_code}.")
        return parse_directory(res.json())

    def check(self, issue_ref, pan):
        res = self.http.get(CHECK + issue_ref, params={"pan": pan}, headers={"Origin": SITE, "Referer": SITE + "/"})
        if res.status_code == 404:
            return CheckResult(Outcome.NOT_FOUND, message="No application found for this PAN.")
        if res.status_code == 429:
            return CheckResult(Outcome.ERROR, message="Maashitla is rate-limiting requests. Try again in a minute.")
        if res.status_code != 200:
            raise RegistrarError(f"Maashitla returned {res.status_code}.")
        return parse_check(res.json())
