"""
Client and parsers for NSE's public IPO endpoints.

These are the JSON endpoints nseindia.com's own pages call. They are not a
documented API: NSE rejects requests without a browser-like User-Agent and
without the cookies its HTML pages set, so the client "primes" a session by
loading a page first. Field names were taken from real responses, saved
under tests/fixtures/nse/.

Parsing is kept in pure functions so it can be tested without a network.
"""

import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import httpx

BASE = "https://www.nseindia.com"
PRIME_PAGE = f"{BASE}/market-data/all-upcoming-issues-ipo"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Equity series only. NSE also lists debt (DEBT), InvITs (IV), REITs (RR)
# and a long tail of bond series through the same endpoints.
EQUITY_SERIES = {"EQ", "BE", "SME"}


class NSEError(Exception):
    pass


@dataclass
class IssueRecord:
    symbol: str
    name: str
    series: str
    open_date: date | None
    close_date: date | None
    price_band_low: Decimal | None
    price_band_high: Decimal | None
    listing_date: date | None = None
    lot_size: int | None = None
    registrar_name: str | None = None

    @property
    def is_sme(self) -> bool:
        return self.series == "SME"


# ----------------------------------------------------------------- parsing

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def parse_date(value: str | None) -> date | None:
    """'05-Oct-2026' or '30-SEP-2026' → date. '-' and blanks → None."""
    value = (value or "").strip()
    if not value or value == "-":
        return None
    try:
        return datetime.strptime(value, "%d-%b-%Y").date()
    except ValueError:
        return None


def parse_price_range(value: str | None) -> tuple[Decimal | None, Decimal | None]:
    """
    'Rs.208 to Rs.220' → (208, 220). Fixed-price issues ('Rs.1000') give
    the same number twice. Tolerates NSE's variants like 'Rs. 70/- to Rs. 75/-'.
    """
    nums = [Decimal(n.replace(",", "")) for n in _NUM.findall(value or "")]
    if not nums:
        return None, None
    return nums[0], nums[-1] if len(nums) > 1 else nums[0]


def parse_int(value: str | None) -> int | None:
    m = _NUM.search(value or "")
    return int(Decimal(m.group().replace(",", ""))) if m else None


def parse_list_row(row: dict) -> IssueRecord | None:
    """One row from all-upcoming-issues or public-past-issues. None if not equity."""
    series = (row.get("series") or row.get("securityType") or "").strip()
    symbol = (row.get("symbol") or "").strip()
    if series not in EQUITY_SERIES or not symbol:
        return None
    low, high = parse_price_range(row.get("issuePrice") if "series" in row else row.get("priceRange"))
    return IssueRecord(
        symbol=symbol,
        name=(row.get("companyName") or row.get("company") or symbol).strip(),
        series=series,
        open_date=parse_date(row.get("issueStartDate") or row.get("ipoStartDate")),
        close_date=parse_date(row.get("issueEndDate") or row.get("ipoEndDate")),
        price_band_low=low,
        price_band_high=high,
        listing_date=parse_date(row.get("listingDate")),
    )


def parse_detail(payload: dict) -> dict:
    """ipo-detail → {'lot_size', 'registrar_name', 'price_band_low', 'price_band_high'}."""
    info = {
        (r.get("title") or "").strip(): (r.get("value") or "").strip().strip('"')
        for r in (payload.get("issueInfo") or {}).get("dataList", [])
        if r.get("title")
    }
    # Mainboard pages say "Bid Lot"; SME pages say "Lot Size".
    lot = info.get("Bid Lot") or info.get("Lot Size") or info.get("Minimum Order Quantity")
    low, high = parse_price_range(info.get("Price Range"))
    return {
        "lot_size": parse_int(lot),
        "registrar_name": info.get("Name of the Registrar") or None,
        "price_band_low": low,
        "price_band_high": high,
    }


# ------------------------------------------------------------------ client

class NSEClient:
    def __init__(self, http: httpx.Client | None = None, retries: int = 3, pause: float = 1.0):
        self.http = http or httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True)
        self.retries = retries
        self.pause = pause
        self._primed = False

    def _prime(self) -> None:
        self.http.get(PRIME_PAGE, headers={"Accept": "text/html"})
        self._primed = True

    def _get(self, path: str, params: dict | None = None):
        last: Exception | None = None
        for attempt in range(self.retries):
            if not self._primed:
                self._prime()
            try:
                res = self.http.get(
                    f"{BASE}/api/{path}", params=params,
                    headers={"Accept": "application/json", "Referer": f"{BASE}/"},
                )
                if res.status_code in (401, 403):
                    # Session cookies expired — get fresh ones and retry.
                    self._primed = False
                    raise NSEError(f"NSE refused {path} ({res.status_code})")
                res.raise_for_status()
                return res.json()
            except (httpx.HTTPError, ValueError, NSEError) as exc:
                last = exc
                time.sleep(self.pause * (attempt + 1))
        raise NSEError(f"NSE request failed: {path}: {last}")

    def upcoming(self) -> list[IssueRecord]:
        rows = self._get("all-upcoming-issues", {"category": "ipo"})
        return [r for r in map(parse_list_row, rows or []) if r]

    def past(self) -> list[IssueRecord]:
        rows = self._get("public-past-issues")
        return [r for r in map(parse_list_row, rows or []) if r]

    def detail(self, symbol: str, series: str) -> dict:
        return parse_detail(self._get("ipo-detail", {"symbol": symbol, "series": series}))
