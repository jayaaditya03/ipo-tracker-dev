from .base import CheckResult, Outcome, RegistrarAdapter, RegistrarError
from .bigshare import BigshareAdapter
from .kfin import KfinAdapter
from .maashitla import MaashitlaAdapter
from .mufg import MufgIntimeAdapter
from .skyline import SkylineAdapter

ADAPTERS: dict[str, type[RegistrarAdapter]] = {
    a.slug: a for a in (MufgIntimeAdapter, BigshareAdapter, KfinAdapter, MaashitlaAdapter, SkylineAdapter)
}

__all__ = ["ADAPTERS", "CheckResult", "Outcome", "RegistrarAdapter", "RegistrarError"]
