"""
Common interface for registrar allotment lookups.

Each registrar runs its own public status page with its own private API.
An adapter wraps one of them behind two calls:

    issues()             → the issues the registrar currently lists, as
                           (registrar's own id, name) pairs
    check(issue_ref, pan) → what the registrar says about that PAN

Adapters never log or raise with the PAN in the message.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

import httpx

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")


class Outcome(StrEnum):
    ALLOTTED = "allotted"           # shares_allotted > 0
    NOT_ALLOTTED = "not_allotted"   # applied, nothing allotted
    NOT_FOUND = "not_found"         # registrar has no application for this PAN
    NOT_PUBLISHED = "not_published" # registrar does not list this issue (yet)
    UNSUPPORTED = "unsupported"     # no adapter for this registrar
    ERROR = "error"                 # network trouble, rate limit, unexpected reply


@dataclass
class CheckResult:
    outcome: Outcome
    shares_applied: int | None = None
    shares_allotted: int | None = None
    message: str = ""


class RegistrarError(Exception):
    pass


def to_int(value) -> int:
    """'1,200' / ' 43 ' / 43 / '' → int (0 for blanks)."""
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else 0


def result_from_shares(applied: int, allotted: int) -> CheckResult:
    if allotted > 0:
        return CheckResult(Outcome.ALLOTTED, applied, allotted)
    return CheckResult(Outcome.NOT_ALLOTTED, applied, 0)


_NOISE = re.compile(r"\b(LIMITED|LTD|PRIVATE|PVT|SME|IPO|THE|INDIA)\b")


def normalise_name(name: str) -> str:
    """'Shah Investor's Home Limited - IPO' → 'SHAH INVESTORS HOME'."""
    name = name.upper().replace("&", " AND ")
    name = re.sub(r"[^A-Z0-9 ]", "", name)
    return " ".join(_NOISE.sub(" ", name).split())


class RegistrarAdapter:
    slug: str = ""

    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)

    def issues(self) -> list[tuple[str, str]]:
        raise NotImplementedError

    def check(self, issue_ref: str, pan: str) -> CheckResult:
        raise NotImplementedError

    def find_issue(self, name: str) -> str | None:
        """Match our IPO name against the registrar's dropdown."""
        target = normalise_name(name)
        if not target:
            return None
        candidates = [(ref, normalise_name(n)) for ref, n in self.issues()]
        for ref, n in candidates:
            if n == target:
                return ref
        # Prefix match catches "Runwal Enterprise" vs "Runwal Enterprises",
        # but only on names long enough not to collide ("ABC" vs "ABC Infra").
        for ref, n in candidates:
            if min(len(n), len(target)) >= 8 and (n.startswith(target) or target.startswith(n)):
                return ref
        return None
