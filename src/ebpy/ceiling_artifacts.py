"""Classify the two files that together hold the ceiling contract.

Neither artifact can reconstruct the other. Commands therefore share one
fail-closed decision instead of each guessing from the fragment it happens to
read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .baseline import Ceiling, analyzers_in, read_ceiling, rule_totals
from .models import CellCounts, RuleId, State
from .state import Ledger, read_ledger

ArtifactKind = Literal["fresh", "frozen", "invalid"]

_PRE_FREEZE_PHASES = ("diagnose", "bootstrap", "freeze")
_POST_FREEZE_PHASES = ("drain", "tighten", "split", "review")


@dataclass(frozen=True)
class CeilingArtifacts:
    """The only three states the ceiling files may occupy as a pair."""

    kind: ArtifactKind
    ledger: Ledger
    cells: CellCounts
    detail: str | None = None


def invalid_artifacts_message(artifacts: CeilingArtifacts) -> str:
    assert artifacts.detail is not None
    return "\n".join(
        [
            f"Ceiling artifacts are invalid: {artifacts.detail}.",
            "ebpy will not guess at or reconstruct a ceiling from partial data.",
            "Restore the matching .ebpy/baseline.json and .ebpy/state.json, or run",
            "`ebpy freeze --force` to discard the old contract and pin today's measurements.",
        ]
    )


def _fresh_state(state: State) -> bool:
    return (
        state.frozen_at is None
        and not state.rules
        and not state.frozen_analyzers
        and state.phase in _PRE_FREEZE_PHASES
    )


def _frozen_state(state: State) -> bool:
    return state.frozen_at is not None and state.phase in _POST_FREEZE_PHASES


def _ledger_rule_ceilings(state: State) -> dict[RuleId, int]:
    return {name: rule.baseline for name, rule in state.rules.items() if rule.baseline > 0}


def _validate_frozen_pair(cells: CellCounts, state: State) -> tuple[ArtifactKind, str | None]:
    """The three ways a frozen pair's data can still disagree.

    Checked in this order because an analyzer missing from the roster always makes the
    rule-totals comparison disagree too (its cells have nowhere to be accounted for in the
    ledger) — checking totals first would shadow the roster-specific detail with the more
    generic "disagree" message.
    """
    if not state.frozen_analyzers:
        return "invalid", ".ebpy/state.json records a freeze but no analyzers"
    unrostered = analyzers_in(cells) - set(state.frozen_analyzers)
    if unrostered:
        return (
            "invalid",
            ".ebpy/baseline.json holds cells for an analyzer the ledger does not record freezing",
        )
    if rule_totals(cells) != _ledger_rule_ceilings(state):
        return "invalid", "the ceilings in .ebpy/baseline.json and .ebpy/state.json disagree"
    return "frozen", None


def _classify_missing_ceiling(ledger: Ledger) -> CeilingArtifacts:
    state = ledger.state
    if not ledger.exists or (state is not None and _fresh_state(state)):
        return CeilingArtifacts("fresh", ledger, {})
    return CeilingArtifacts(
        "invalid", ledger, {}, ".ebpy/state.json contains ceiling data but .ebpy/baseline.json is missing"
    )


def _classify_paired(cells: CellCounts, ledger: Ledger) -> CeilingArtifacts:
    state = ledger.state
    assert state is not None
    if not _frozen_state(state):
        unfrozen_detail = ".ebpy/baseline.json exists but .ebpy/state.json does not record a valid freeze"
        return CeilingArtifacts("invalid", ledger, cells, unfrozen_detail)
    kind, detail = _validate_frozen_pair(cells, state)
    return CeilingArtifacts(kind, ledger, cells, detail)


def _classify_readable(ceiling: Ceiling, ledger: Ledger) -> CeilingArtifacts:
    cells = ceiling.cells or {}
    if not ceiling.exists:
        return _classify_missing_ceiling(ledger)
    if not ledger.exists:
        return CeilingArtifacts(
            "invalid", ledger, cells, ".ebpy/baseline.json exists but .ebpy/state.json is missing"
        )
    return _classify_paired(cells, ledger)


def read_ceiling_artifacts(cwd: Path) -> CeilingArtifacts:
    """Read and classify both files without inferring missing contract data."""
    ceiling = read_ceiling(cwd)
    ledger = read_ledger(cwd)

    if ceiling.exists and ceiling.cells is None:
        return CeilingArtifacts("invalid", ledger, {}, ".ebpy/baseline.json is unreadable")
    if ledger.exists and ledger.state is None:
        return CeilingArtifacts("invalid", ledger, ceiling.cells or {}, ".ebpy/state.json is unreadable")
    return _classify_readable(ceiling, ledger)
