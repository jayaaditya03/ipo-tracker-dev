"""
Upsert NSE's IPO listings into the IPO table.

Rules:
  * Key on symbol (unique when set), falling back to a case-insensitive
    name match for issues that were entered by hand before they had one.
  * Never replace a value with nothing — NSE omits fields on some rows, and
    a hand-entered listing price must survive a sync.
  * Allotment and listing dates are not published by NSE. When missing,
    estimate them from SEBI's T+3 timeline (allotment T+1, listing T+3
    working days after close) and flag the row as estimated.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from ipos.models import IPO

from .nse import IssueRecord, NSEClient, NSEError
from .registrars import ensure_known_registrars, resolve_registrar

log = logging.getLogger(__name__)


@dataclass
class SyncReport:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)


def add_working_days(start: date, days: int) -> date:
    """Skips weekends. Exchange holidays are not modelled — hence 'estimated'."""
    d = start
    while days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days -= 1
    return d


def sync_from_nse(client: NSEClient | None = None, *, past_days: int = 90,
                  today: date | None = None, detail_pause: float = 0.5) -> SyncReport:
    client = client or NSEClient()
    today = today or timezone.localdate()
    report = SyncReport()
    ensure_known_registrars()

    # Upcoming first so its fresher rows win the de-duplication below.
    records: dict[str, IssueRecord] = {}
    cutoff = today - timedelta(days=past_days)
    for rec in client.upcoming() + [r for r in client.past() if r.open_date and r.open_date >= cutoff]:
        records.setdefault(rec.symbol, rec)

    for rec in records.values():
        try:
            outcome = _upsert(client, rec, detail_pause, today)
        except NSEError as exc:
            report.errors.append(f"{rec.symbol}: {exc}")
            continue
        if outcome == "created":
            report.created.append(rec.name)
        elif outcome == "updated":
            report.updated.append(rec.name)
        else:
            report.unchanged += 1
    return report


def _find_existing(rec: IssueRecord) -> IPO | None:
    return (IPO.objects.filter(symbol=rec.symbol).first()
            or IPO.objects.filter(symbol="", name__iexact=rec.name).first())


def _upsert(client: NSEClient, rec: IssueRecord, detail_pause: float, today: date) -> str:
    ipo = _find_existing(rec)
    is_new = ipo is None

    # The detail call is the slow part; only make it when we lack what it
    # provides.
    needs_detail = is_new or not ipo.lot_size or ipo.registrar.slug == "unknown"
    detail: dict = {}
    if needs_detail:
        try:
            detail = client.detail(rec.symbol, rec.series)
        except NSEError as exc:
            log.warning("No detail for %s: %s", rec.symbol, exc)
        time.sleep(detail_pause)

    values = {
        "name": rec.name,
        "symbol": rec.symbol,
        "board": IPO.Board.SME if rec.is_sme else IPO.Board.MAINBOARD,
        "open_date": rec.open_date,
        "close_date": rec.close_date,
        "price_band_low": detail.get("price_band_low") or rec.price_band_low,
        "price_band_high": detail.get("price_band_high") or rec.price_band_high,
        "lot_size": detail.get("lot_size"),
        "listing_date": rec.listing_date,
    }

    if is_new:
        ipo = IPO(source=IPO.Source.NSE, registrar=resolve_registrar(detail.get("registrar_name")))
    elif detail.get("registrar_name"):
        ipo.registrar = resolve_registrar(detail["registrar_name"])

    before = _snapshot(ipo)
    for name, value in values.items():
        if value not in (None, ""):        # never overwrite with nothing
            setattr(ipo, name, value)

    if ipo.close_date and (not ipo.allotment_date or ipo.dates_estimated):
        ipo.allotment_date = add_working_days(ipo.close_date, 1)
        ipo.refund_date = add_working_days(ipo.close_date, 2)
        if not rec.listing_date:
            ipo.listing_date = add_working_days(ipo.close_date, 3)
        ipo.dates_estimated = not rec.listing_date

    if ipo.status != IPO.Status.WITHDRAWN:
        ipo.status = ipo.derive_status(today)

    if not is_new and _snapshot(ipo) == before:
        return "unchanged"

    ipo.last_synced_at = timezone.now()
    with transaction.atomic():
        ipo.save()
    return "created" if is_new else "updated"


_TRACKED = ["name", "symbol", "board", "status", "registrar_id", "price_band_low", "price_band_high",
            "lot_size", "open_date", "close_date", "allotment_date", "refund_date", "listing_date"]


def _snapshot(ipo: IPO) -> tuple:
    return tuple(getattr(ipo, f) for f in _TRACKED)
