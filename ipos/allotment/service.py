"""
Check allotment for a batch of applications and record what the registrars say.

One adapter instance per registrar per batch, so the registrar's issue list
is fetched at most once, and the matched id is cached on IPO.registrar_ref
so later batches skip that lookup entirely.

Results are written through Application.mark_status(source=REGISTRAR), the
same audited path as a manual update. An error on one PAN never stops the
rest of the batch, and a registrar that fails several times in a row is
skipped for the rest of it rather than asked again for every PAN.
"""

import logging
import time
from collections.abc import Iterable

import httpx
from django.db import transaction
from django.utils import timezone

from ipos.models import Application, StatusEvent

from . import ADAPTERS
from .base import CheckResult, Outcome, RegistrarAdapter, RegistrarError

log = logging.getLogger(__name__)

# Applications worth asking about. Already-resolved ones are skipped unless
# explicitly requested — the answer will not change.
CHECKABLE = {Application.Status.APPLIED}

# Consecutive errors after which a registrar is skipped for the rest of the
# batch. With a 30s timeout, 25 PANs against a dead site would otherwise
# hold a request (or the evening job) for over ten minutes.
MAX_CONSECUTIVE_ERRORS = 3


def _apply(app: Application, result: CheckResult) -> bool:
    """
    Translate a registrar answer into a status change on the application.

    The row is locked and re-read first: a check takes seconds per PAN, and
    in that time the user may have set the status by hand, or a second
    check (the evening job and a click in the UI) may have got there first.
    If the status moved on, the newer state wins and this answer is
    dropped. Returns False in that case.
    """
    if result.outcome == Outcome.ALLOTTED:
        full = result.shares_allotted >= (result.shares_applied or app.shares_applied)
        new_status = Application.Status.ALLOTTED if full else Application.Status.PARTIAL
        shares = result.shares_allotted
    elif result.outcome == Outcome.NOT_ALLOTTED:
        new_status, shares = Application.Status.REJECTED, 0
    else:
        app.checked_at = timezone.now()
        app.save(update_fields=["checked_at", "updated_at"])
        return True

    # The registrar knows how many shares were really bid for — correct the
    # lot count (it is a guess of 1 for applications recorded after the fact).
    lot = app.ipo.lot_size
    if result.shares_applied and lot and result.shares_applied % lot == 0:
        app.lots = result.shares_applied // lot

    note = f"Registrar: {result.shares_allotted or 0} of {result.shares_applied or '?'} shares allotted."
    with transaction.atomic():
        current = Application.objects.select_for_update().only("status").get(pk=app.pk)
        if current.status != app.status:
            app.status = current.status
            return False
        event = app.mark_status(new_status, source=StatusEvent.Source.REGISTRAR, note=note, shares=shares)
        app.checked_at = timezone.now()
        app.save()
        if event:
            event.save()
    return True


def check_applications(apps: Iterable[Application], *, adapters: dict | None = None,
                       pause: float = 1.0) -> list[dict]:
    adapters = adapters if adapters is not None else ADAPTERS
    instances: dict[str, RegistrarAdapter] = {}
    rows: list[dict] = []
    last_call: dict[str, float] = {}
    refs: dict[int, str | None] = {}          # ipo id → registrar's id, looked up once per batch
    failures: dict[str, int] = {}             # registrar slug → consecutive errors

    for app in apps:
        ipo = app.ipo
        slug = ipo.registrar.slug
        row = {
            "application_id": app.id, "ipo_id": ipo.id, "ipo_name": ipo.name,
            "pan_label": app.pan.label, "pan_masked": app.pan.pan_masked,
            "registrar": ipo.registrar.name, "status_check_url": ipo.registrar.status_check_url,
        }

        adapter_cls = adapters.get(slug)
        if adapter_cls is None:
            rows.append({**row, "outcome": Outcome.UNSUPPORTED, "status": app.status,
                         "message": f"Automatic checks aren't available for {ipo.registrar.name}. "
                                    "Use the registrar's site."})
            continue
        if failures.get(slug, 0) >= MAX_CONSECUTIVE_ERRORS:
            rows.append({**row, "outcome": Outcome.ERROR, "status": app.status,
                         "message": f"Skipped: {ipo.registrar.name} failed {MAX_CONSECUTIVE_ERRORS} times "
                                    "in a row. Try again later."})
            continue

        try:
            adapter = instances.setdefault(slug, adapter_cls())
            if not ipo.registrar_ref:
                if ipo.id not in refs:
                    refs[ipo.id] = adapter.find_issue(ipo.name)
                ref = refs[ipo.id]
                if ref is None:
                    closed_long_ago = ipo.close_date and (timezone.localdate() - ipo.close_date).days > 5
                    message = (
                        f"{ipo.registrar.name} has taken this issue off its status page (registrars only "
                        "keep recent issues). Check your demat holdings or the bank's ASBA refund instead."
                        if closed_long_ago else
                        f"{ipo.registrar.name} doesn't list this issue yet — results are usually out "
                        "the day after it closes."
                    )
                    rows.append({**row, "outcome": Outcome.NOT_PUBLISHED, "status": app.status,
                                 "message": message})
                    continue
                ipo.registrar_ref = ref
                ipo.save(update_fields=["registrar_ref", "updated_at"])

            # Be polite: at most one request a second per registrar.
            wait = pause - (time.monotonic() - last_call.get(slug, 0))
            if wait > 0:
                time.sleep(wait)
            last_call[slug] = time.monotonic()

            result = adapter.check(ipo.registrar_ref, app.pan.pan)
        except RegistrarError as exc:
            result = CheckResult(Outcome.ERROR, message=str(exc))
        except httpx.HTTPError as exc:
            # Deliberately not logging the request or the exception text —
            # both can contain the PAN.
            log.warning("Allotment check failed for application %s: %s", app.id, type(exc).__name__)
            result = CheckResult(Outcome.ERROR, message=f"Couldn't reach {ipo.registrar.name}. Try again later.")
        except Exception as exc:  # noqa: BLE001 — a changed site must not abort the batch
            # Usually the registrar changed its page or reply format.
            log.error("Unexpected reply checking application %s with %s: %s",
                      app.id, slug, type(exc).__name__)
            result = CheckResult(Outcome.ERROR, message=f"{ipo.registrar.name} sent a reply this app doesn't "
                                                        "understand. Its site may have changed.")

        if result.outcome == Outcome.ERROR:
            failures[slug] = failures.get(slug, 0) + 1
        else:
            failures[slug] = 0

        message = result.message
        if not _apply(app, result):
            message = "Not recorded: this application was updated while the check ran."
        rows.append({**row, "outcome": result.outcome, "status": app.status,
                     "shares_applied": result.shares_applied, "shares_allotted": result.shares_allotted,
                     "message": message})
    return rows
