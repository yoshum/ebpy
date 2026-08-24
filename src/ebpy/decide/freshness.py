"""A diagnosis is a photograph, and the repository keeps moving.

An agent picking the ledger up weeks later has no way to tell whether "23 files
over the limit" is today's number or one taken before a rewrite — so the ledger
records WHEN and AT WHICH COMMIT it was taken, and this decides whether it can
still be trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Enough churn that any file-level observation is likely to name something that has moved.
STALE_COMMIT_COUNT = 50

# Long enough that the dependency tree, and therefore the rule set, has probably changed.
STALE_DAY_COUNT = 30


@dataclass(frozen=True)
class FreshnessInput:
    """What deciding freshness needs: when and where the diagnosis was taken, and how far HEAD has moved."""

    diagnosed_at: str | None
    diagnosed_commit: str | None
    head_commit: str | None
    # Commits on HEAD that the diagnosis never saw. None when it could not be computed.
    commits_since: int | None
    now: datetime


@dataclass(frozen=True)
class Freshness:
    """Whether the diagnosis is stale, and the reason to show if it is."""

    stale: bool
    reason: str


def _days_between(from_iso: str, to: datetime) -> int | None:
    try:
        start = datetime.fromisoformat(from_iso)
    except ValueError:
        return None
    return (to - start).days


def assess_freshness(inp: FreshnessInput) -> Freshness:
    """Decide whether a recorded diagnosis can still be trusted given its age and the commits since."""
    if not inp.diagnosed_at or not inp.diagnosed_commit:
        return Freshness(stale=True, reason="never diagnosed — run `ebpy diagnose --write` first")
    age = _days_between(inp.diagnosed_at, inp.now)
    if age is not None and age >= STALE_DAY_COUNT:
        return Freshness(
            stale=True, reason=f"diagnosis is {age} days old; re-run diagnose before trusting it"
        )
    if inp.commits_since is not None and inp.commits_since >= STALE_COMMIT_COUNT:
        return Freshness(
            stale=True,
            reason=f"{inp.commits_since} commits since the diagnosis; re-run diagnose before trusting it",
        )
    if inp.head_commit and inp.head_commit != inp.diagnosed_commit and inp.commits_since is None:
        return Freshness(stale=True, reason="HEAD moved since the diagnosis and the distance is unknown")
    return Freshness(stale=False, reason="current")
