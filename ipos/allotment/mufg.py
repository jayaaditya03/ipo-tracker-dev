"""
MUFG Intime (formerly Link Intime) — in.mpms.mufg.com.

The page's own flow, reproduced:
  1. IPO.aspx/GetDetails      → XML list of <company_id>, <companyname>
  2. IPO.aspx/generateToken   → a token the page AES-encrypts client-side
                                (key and IV are hardcoded in the page)
  3. IPO.aspx/SearchOnPan     → XML with <SHARES> applied and <ALLOT> allotted,
                                <Table1><Msg> on error, or an empty
                                <NewDataSet /> when the PAN has no record.
"""

import base64
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .base import CheckResult, Outcome, RegistrarAdapter, RegistrarError, result_from_shares, to_int

BASE = "https://in.mpms.mufg.com/Initial_Offer/"
JSON = {"Content-Type": "application/json; charset=utf-8"}
_KEY = b"8080808080808080"      # from the page's encVal(); same value as IV


def encrypt_token(token: str) -> str:
    padder = padding.PKCS7(128).padder()
    data = padder.update(token.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(_KEY), modes.CBC(_KEY)).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode()


def _xml(text: str) -> ET.Element:
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise RegistrarError("MUFG Intime returned unreadable data.") from exc


def parse_companies(xml_text: str) -> list[tuple[str, str]]:
    root = _xml(xml_text)
    return [
        (t.findtext("company_id", "").strip(), t.findtext("companyname", "").strip())
        for t in root.iter("Table")
        if t.findtext("company_id")
    ]


def parse_search(xml_text: str) -> CheckResult:
    root = _xml(xml_text)
    msg = root.find("Table1/Msg")
    if msg is not None:
        text = (msg.text or "").strip()
        if "no record" in text.lower() or "not found" in text.lower():
            return CheckResult(Outcome.NOT_FOUND, message=text)
        return CheckResult(Outcome.ERROR, message=text or "MUFG Intime rejected the request.")
    rows = list(root.iter("Table"))
    if not rows:
        return CheckResult(Outcome.NOT_FOUND, message="No application found for this PAN.")
    applied = sum(to_int(r.findtext("SHARES")) for r in rows)
    allotted = sum(to_int(r.findtext("ALLOT")) for r in rows)
    return result_from_shares(applied, allotted)


class MufgIntimeAdapter(RegistrarAdapter):
    slug = "mufg-intime"

    def _post(self, method: str, body: str) -> str:
        res = self.http.post(BASE + f"IPO.aspx/{method}", headers=JSON, content=body)
        if res.status_code != 200:
            raise RegistrarError(f"MUFG Intime {method} returned {res.status_code}.")
        return res.json()["d"]

    def issues(self):
        self.http.get(BASE + "public-issues.html")      # sets the session cookie
        return parse_companies(self._post("GetDetails", "{}"))

    def check(self, issue_ref, pan):
        token = encrypt_token(str(self._post("generateToken", "{}")))
        # The page sends this single-quoted pseudo-JSON and ASP.NET accepts
        # it. Safe to interpolate: PANs are validated to [A-Z0-9] and the
        # other two values come from the registrar itself.
        body = f"{{'clientid': '{issue_ref}','PAN': '{pan}','IFSC': '','CHKVAL': '1','token': '{token}'}}"
        return parse_search(self._post("SearchOnPan", body))
