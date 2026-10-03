"""
KFin Technologies — ipostatus.kfintech.com.

A React app. Its list of issues is a JSON literal compiled into the JS
bundle, so issues() loads the page, finds main.<hash>.js and extracts it.
The lookup is GET .../api/query?type=pan with the PAN in a `reqparam`
header and the issue in `client_id`. 404 means no record; 200 returns
{"data": [{"App_Shares": .., "All_Shares": ..}, ...]}.
"""

import json
import re

from .base import CheckResult, Outcome, RegistrarAdapter, RegistrarError, result_from_shares, to_int

SITE = "https://ipostatus.kfintech.com/"
API = "https://0uz601ms56.execute-api.ap-south-1.amazonaws.com/prod/api/query"

_BUNDLE = re.compile(r'src="\.?/?(static/js/main\.[0-9a-f]+\.js)"')
_LIST = re.compile(r"JSON\.parse\('(\[\{\"clientId\".*?\])'\)")


def parse_bundle(js: str) -> list[tuple[str, str]]:
    m = _LIST.search(js)
    if not m:
        raise RegistrarError("Could not find KFin's issue list — the site has probably changed.")
    return [(row["clientId"], row["name"]) for row in json.loads(m.group(1).replace("\\'", "'"))]


def parse_result(payload: dict) -> CheckResult:
    rows = payload.get("data") or []
    if not rows:
        return CheckResult(Outcome.NOT_FOUND, message="No application found for this PAN.")
    applied = sum(to_int(r.get("App_Shares")) for r in rows)
    allotted = sum(to_int(r.get("All_Shares")) for r in rows)
    return result_from_shares(applied, allotted)


class KfinAdapter(RegistrarAdapter):
    slug = "kfintech"

    def issues(self):
        page = self.http.get(SITE)
        m = _BUNDLE.search(page.text)
        if not m:
            raise RegistrarError("Could not find KFin's app bundle — the site has probably changed.")
        return parse_bundle(self.http.get(SITE + m.group(1)).text)

    def check(self, issue_ref, pan):
        res = self.http.get(API, params={"type": "pan"},
                            headers={"reqparam": pan, "client_id": issue_ref,
                                     "Origin": SITE.rstrip("/"), "Referer": SITE})
        if res.status_code == 404:
            return CheckResult(Outcome.NOT_FOUND, message="No application found for this PAN.")
        if res.status_code == 429:
            return CheckResult(Outcome.ERROR, message="KFin is rate-limiting requests. Try again in a minute.")
        if res.status_code != 200:
            raise RegistrarError(f"KFin returned {res.status_code}.")
        return parse_result(res.json())
