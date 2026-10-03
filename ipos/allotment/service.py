"""
Check allotment for a batch of applications and record what the registrars say.

One adapter instance per registrar per batch, so the registrar's issue list
is fetched at most once, and the matched id is cached on IPO.registrar_ref
so later batches skip that lookup entirely.

Results are written through Application.mark_status(source=REGISTRAR), the
same audited path as a manual update. An error on one PAN never stops the
rest of the batch.
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


def _apply(app: Application, result: CheckResult) -> None:
    """Translate a registrar answer into a status change on the application."""
    if result.outcome == Outcome.ALLOTTED:
        full = result.shares_allotted >= (result.shares_applied or app.shares_applied)
        new_status = Application.Status.ALLOTTED if full else Application.Status.PARTIAL
        shares = result.shares_allotted
    elif result.outcome == Outcome.NOT_ALLOTTED:
        new_status, shares = Application.Status.REJECTED, 0
    else:
        app.checked_at = timezone.now()
        app.save(update_fields=["checked_at", "updated_at"])
        return

    note = f"Registrar: {result.shares_allotted or 0} of {result.shares_applied or '?'} shares allotted."
    with transaction.atomic():
        event = app.mark_status(new_status, source=StatusEvent.Source.REGISTRAR, note=note, shares=shares)
        app.checked_at = timezone.now()
        app.save()
        if event:
            event.save()


def check_applications(apps: Iterable[Application], *, adapters: dict | None = None,
                       pause: float = 1.0) -> list[dict]:
    adapters = adapters if adapters is not None else ADAPTERS
    instances: dict[str, RegistrarAdapter] = {}
    rows: list[dict] = []
    last_call: dict[str, float] = {}

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
        adapter = instances.setdefault(slug, adapter_cls())

        try:
            if not ipo.registrar_ref:
                ref = adapter.find_issue(ipo.name)
                if ref is None:
                    rows.append({**row, "outcome": Outcome.NOT_PUBLISHED, "status": app.status,
                                 "message": f"{ipo.registrar.name} doesn't list this issue yet — "
                                            "results are usually out the day after it closes."})
                    continue
                ipo.registrar_ref = ref
                ipo.save(update_fields=["registrar_ref", "updated_at"])

            # Be polite: at most one request a second per registrar.
            wait = pause - (time.monotonic() - last_call.get(slug, 0))
            if wait > 0:
                time.sleep(wait)
            last_call[slug] = time.monotonic()

            result = adapter.check(ipo.registrar_ref, app.pan.pan)
        except (RegistrarError, httpx.HTTPError, ValueError, KeyError) as exc:
            # Deliberately not logging the request — it contains the PAN.
            log.warning("Allotment check failed for application %s: %s", app.id, type(exc).__name__)
            result = CheckResult(Outcome.ERROR, message=str(exc) if isinstance(exc, RegistrarError)
                                 else f"Couldn't reach {ipo.registrar.name}. Try again later.")

        _apply(app, result)
        rows.append({**row, "outcome": result.outcome, "status": app.status,
                     "shares_applied": result.shares_applied, "shares_allotted": result.shares_allotted,
                     "message": result.message})
    return rows
