"""Classify the two files that together hold the ceiling contract.

Neither artifact can reconstruct the other. Commands therefore share one
fail-closed decision instead of each guessing from the fragment it happens to
read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .baseline import Ceiling, analyzers_in, cells_for, read_ceiling, rule_totals
from .state import Ledger, read_ledger, replace_analyzer_rules

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from ebpy.models import CellCounts, CellCountsView, RuleId, State

    from .config import EbpyConfig

ArtifactKind = Literal["fresh", "frozen", "invalid"]

_PRE_FREEZE_PHASES = ("diagnose", "bootstrap", "freeze")
_POST_FREEZE_PHASES = ("drain", "tighten", "split", "review")


def reconcile_scope(config: EbpyConfig | None, state: State) -> str | None:
    """Return an error message if config and the frozen roster disagree on the analyzer set.

    None means either no config is present (no gate) or the sets match exactly.
    When they differ, the message names each direction of the discrepancy with the
    appropriate remediation command so the caller can surface it without knowing the detail.
    """
    if config is None:
        return None
    declared = set(config.analyzers)
    frozen = set(state.frozen_analyzers)
    if declared == frozen:
        return None
    unfrozen = sorted(declared - frozen)
    undeclared = sorted(frozen - declared)
    lines = [".ebpy/config.json and the frozen contract disagree on the analyzer set:"]
    if unfrozen:
        lines.append(
            f"  declared but not frozen: {', '.join(unfrozen)} — run `ebpy freeze --analyzer <name>`."
        )
    if undeclared:
        lines.append(
            f"  frozen but not declared: {', '.join(undeclared)}"
            " — re-declare it, or `ebpy freeze --force` to drop it."
        )
    return "\n".join(lines)


@dataclass(frozen=True)
class CeilingArtifacts:
    """The only three states the ceiling files may occupy as a pair."""

    kind: ArtifactKind
    ledger: Ledger
    cells: CellCounts
    detail: str | None = None
    legacy_version: int | None = None


def invalid_artifacts_message(artifacts: CeilingArtifacts) -> str:
    assert artifacts.detail is not None
    if artifacts.legacy_version is not None:
        return _legacy_artifacts_message(artifacts.legacy_version)
    return "\n".join(
        [
            f"Ceiling artifacts are invalid: {artifacts.detail}.",
            "ebpy will not guess at or reconstruct a ceiling from partial data.",
            "Restore the matching .ebpy/baseline.json and .ebpy/state.json, or run",
            "`ebpy freeze --force` to discard the old contract and pin today's measurements.",
        ]
    )


def _legacy_artifacts_message(version: int) -> str:
    """A repository frozen by a retired ebpy: an old format, not corrupt bytes.

    `ebpy freeze --force` is the only way forward, and it starts from an empty state — so it
    discards not just the old ceiling but the work log, the last diagnosis and the commit it
    was taken at. The user must know that before running it, not discover it after.
    """
    return "\n".join(
        [
            f".ebpy/state.json is version {version}, which this ebpy no longer reads.",
            "There is no migration: re-pin today's measurements with `ebpy freeze --force`.",
            "That discards the old contract and its history — the work log, the last diagnosis",
            "and the commit it was taken at are lost along with the ceiling.",
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


def align_analyzer_rules_to_cells(state: State, analyzer_cells: CellCountsView, analyzer: str) -> State:
    """Reinstall `analyzer`'s ledger rule totals from the very cells being written for it.

    The write-side counterpart to `_validate_frozen_pair`: rather than let each command
    re-derive the ledger totals by hand and hope the arithmetic matches, the one derivation
    the read side checks — per-rule totals equal `rule_totals` of the analyzer's cells — is
    performed here, so a caller cannot write cells and a divergent ledger. `analyzer_cells`
    holds only this analyzer's namespace (a scoped freeze's fresh cells, a prune's kept cells).

    Uses `replace_analyzer_rules`, so a rule whose findings are all gone leaves the namespace
    instead of lingering at a stale baseline — exactly what keeps the pair consistent.
    """
    return replace_analyzer_rules(state, analyzer, rule_totals(analyzer_cells))


def align_all_analyzer_rules_to_cells(state: State, cells: CellCountsView, analyzers: Iterable[str]) -> State:
    """Align every listed analyzer's ledger totals to its slice of one combined baseline.

    The global-freeze counterpart: `cells` spans every analyzer, so each namespace is carved
    out with `cells_for` before its totals are reinstalled. Mutates and returns `state` in the
    same style as `replace_analyzer_rules`.
    """
    for analyzer in analyzers:
        state = align_analyzer_rules_to_cells(state, cells_for(cells, analyzer), analyzer)
    return state


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

    # A retired-version ledger is named for what it is before either file's generic
    # "unreadable" — a version-1 repository has a version-1 baseline too, and reporting that
    # baseline as merely unreadable would bury the one fact that explains both files.
    if ledger.legacy_version is not None:
        detail = f".ebpy/state.json is version {ledger.legacy_version}, a format this ebpy no longer reads"
        return CeilingArtifacts("invalid", ledger, {}, detail, legacy_version=ledger.legacy_version)
    if ceiling.exists and ceiling.cells is None:
        return CeilingArtifacts("invalid", ledger, {}, ".ebpy/baseline.json is unreadable")
    if ledger.exists and ledger.state is None:
        return CeilingArtifacts("invalid", ledger, ceiling.cells or {}, ".ebpy/state.json is unreadable")
    return _classify_readable(ceiling, ledger)
