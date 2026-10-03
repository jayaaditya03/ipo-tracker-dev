from .base import CheckResult, Outcome, RegistrarAdapter, RegistrarError
from .bigshare import BigshareAdapter
from .kfin import KfinAdapter
from .mufg import MufgIntimeAdapter

ADAPTERS: dict[str, type[RegistrarAdapter]] = {
    a.slug: a for a in (MufgIntimeAdapter, BigshareAdapter, KfinAdapter)
}

__all__ = ["ADAPTERS", "CheckResult", "Outcome", "RegistrarAdapter", "RegistrarError"]
