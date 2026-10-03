"""
Known registrars, and mapping the free-text registrar names exchanges
publish ("MUFG Intime India Private Limited ", "Cameo Corporate Service
Limited") onto our Registrar rows.
"""

import re

from django.utils.text import slugify

from ipos.models import Registrar

# (display name, slug, public allotment-status page)
KNOWN_REGISTRARS = [
    ("MUFG Intime India", "mufg-intime", "https://in.mpms.mufg.com/Initial_Offer/public-issues.html"),
    ("KFin Technologies", "kfintech", "https://ipostatus.kfintech.com/"),
    ("Bigshare Services", "bigshare", "https://ipo.bigshareonline.com/ipo_status.html"),
    ("Maashitla Securities", "maashitla", "https://maashitla.com/allotment-status/public-issues"),
    ("Cameo Corporate Services", "cameo", "https://ipo.cameoindia.com/"),
    ("Skyline Financial Services", "skyline", "https://www.skylinerta.com/ipo.php"),
    ("Purva Sharegistry", "purva", "https://www.purvashare.com/investor-service/ipo-query"),
    ("Integrated Registry", "integrated", "https://ipo.integratedindia.in/"),
]

# Substring in the published name → our slug. "Link Intime" is MUFG
# Intime's former name and still appears on older issues.
ALIASES = [
    ("mufg", "mufg-intime"),
    ("link intime", "mufg-intime"),
    ("kfin", "kfintech"),
    ("karvy", "kfintech"),
    ("bigshare", "bigshare"),
    ("maashitla", "maashitla"),
    ("cameo", "cameo"),
    ("skyline", "skyline"),
    ("purva", "purva"),
    ("integrated registry", "integrated"),
]

UNKNOWN_SLUG = "unknown"

_SUFFIX = re.compile(r"\b(private|pvt\.?|limited|ltd\.?|llp)\b", re.IGNORECASE)


def ensure_known_registrars() -> None:
    for name, slug, url in KNOWN_REGISTRARS:
        Registrar.objects.get_or_create(slug=slug, defaults={"name": name, "status_check_url": url})


def resolve_registrar(published_name: str | None) -> Registrar:
    """Find or create the Registrar for a name as an exchange prints it."""
    raw = (published_name or "").strip()
    lowered = raw.lower()

    for needle, slug in ALIASES:
        if needle in lowered:
            known = next(k for k in KNOWN_REGISTRARS if k[1] == slug)
            obj, _ = Registrar.objects.get_or_create(
                slug=slug, defaults={"name": known[0], "status_check_url": known[2]},
            )
            return obj

    if not raw:
        obj, _ = Registrar.objects.get_or_create(
            slug=UNKNOWN_SLUG, defaults={"name": "Unknown registrar", "is_active": False},
        )
        return obj

    clean = " ".join(_SUFFIX.sub("", raw).split()) or raw
    obj, _ = Registrar.objects.get_or_create(slug=slugify(clean)[:60], defaults={"name": clean[:120]})
    return obj
