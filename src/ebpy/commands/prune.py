"""After a fix, reclaim the ceiling you earned. The only way the ceiling comes down."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..errors import CommandError
from ..measurement import (
    AnalyzerStatus,
    Failed,
    Measured,
    Measurement,
    Observation,
    Unavailable,
    classify,
)
from ..models import AnalysisMeasurement, CellCounts, State
from ..quality_file import write_quality_file
from ..store.baseline import cells_for, finding_total, merge_cells, prune_cells, write_cells
from ..store.ceiling_artifacts import (
    align_analyzer_rules_to_cells,
    invalid_artifacts_message,
    read_ceiling_artifacts,
)
from ..store.state import (
    copy_state,
    total_violations,
    write_state,
)
from ..tools import measure_repository

NO_FROZEN_CEILING = "\n".join(
    [
        "Refusing to prune: no frozen ceiling is recorded yet.",
        "Run `ebpy freeze` first; prune can only lower a ceiling that already exists.",
    ]
)


@dataclass(frozen=True)
class PruneDecision:
    cells: CellCounts
    state: State
    message: str


def _analyzer_note(analyzer: str, reclaimed: int, baseline_total: int, pruned_total: int) -> str:
    if reclaimed > 0:
        return f"  {analyzer}: {baseline_total} -> {pruned_total} (-{reclaimed})"
    return f"  {analyzer}: {baseline_total} (unchanged)"


def _carry_reason(
    analyzer: str, status: AnalyzerStatus, observation: Observation[AnalysisMeasurement] | None
) -> str:
    """Why this analyzer's ceiling could not be lowered — for the message that says so.

    "no-runner" is a contract analyzer this build has no runner for (observation is None);
    an Unavailable/Failed is a tool that could not run; "incomplete" is a Measured that left
    a file unparsed. Each carries a different reason a reader needs to see it verbatim.
    """
    if status == "no-runner":
        return f"{analyzer} has no runner in this ebpy build"
    if isinstance(observation, Unavailable | Failed):
        return observation.detail
    return f"{analyzer} left a file unparsed, so its ceiling could not be verified"


@dataclass(frozen=True)
class _AnalyzerPrune:
    """One analyzer's contribution to a prune: its cells, ceiling totals, and report lines.

    `carry_reason` is set only when the analyzer could not be measured, so its ceiling was
    carried through rather than lowered.
    """

    analyzer: str
    complete: bool
    cells: CellCounts
    note: str
    baseline_total: int
    final_total: int
    carry_reason: str | None


def _prune_one_analyzer(
    analyzer: str, observation: Observation[AnalysisMeasurement] | None, baseline: CellCounts
) -> _AnalyzerPrune:
    """Lower one analyzer's ceiling from its measurement, or carry it through untouched.

    A complete measurement prunes the analyzer's cells to what still exists; any other
    status leaves the baseline cells in place, since a ceiling nobody re-measured cannot
    be lowered.
    """
    status = classify(observation)
    baseline_cells = cells_for(baseline, analyzer)
    baseline_total = finding_total(baseline_cells)

    if status == "complete":
        assert isinstance(observation, Measured)
        current_cells = cells_for(observation.value.cells, analyzer)
        pruned = prune_cells(baseline_cells, current_cells)
        pruned_total = finding_total(pruned)
        reclaimed = baseline_total - pruned_total
        note = _analyzer_note(analyzer, reclaimed, baseline_total, pruned_total)
        return _AnalyzerPrune(analyzer, True, pruned, note, baseline_total, pruned_total, None)

    return _AnalyzerPrune(
        analyzer,
        False,
        baseline_cells,
        f"  {analyzer}: {baseline_total} (not measured)",
        baseline_total,
        baseline_total,
        f"  {analyzer}: not measured — {_carry_reason(analyzer, status, observation)}",
    )


def prune_measurement(
    previous: State,
    baseline: CellCounts,
    measurement: Measurement,
) -> PruneDecision:
    """Lower each complete analyzer's ceiling from measured facts without writing it.

    Analyzers that could not be measured carry their baseline cells and state rules
    through unchanged — their ceilings are not lowered and not lost.
    """
    state = copy_state(previous)
    prunes = [
        _prune_one_analyzer(analyzer, measurement.analyzers.get(analyzer), baseline)
        for analyzer in sorted(previous.frozen_analyzers)
    ]
    for prune in prunes:
        if prune.complete:
            # A rule whose findings are all gone must leave the namespace so the ledger stops
            # naming a ceiling the baseline file no longer carries; the helper's use of
            # `replace_analyzer_rules` (not a rule-by-rule lowering) is what drops it.
            state = align_analyzer_rules_to_cells(state, prune.cells, prune.analyzer)

    cells = merge_cells([prune.cells for prune in prunes])
    analyzer_notes = [prune.note for prune in prunes]
    incomplete_reasons = [prune.carry_reason for prune in prunes if prune.carry_reason is not None]
    total_before = sum(prune.baseline_total for prune in prunes)
    total_after = sum(prune.final_total for prune in prunes)
    reclaimed = total_before - total_after

    if incomplete_reasons and reclaimed == 0:
        # Nothing came down and some analyzer went unmeasured: lead with why the ceiling held.
        summary_lines = [
            f"Nothing reclaimed. {total_violations(previous)} still grandfathered.",
            "Some analyzers could not be measured; their ceilings were left unchanged:",
            *incomplete_reasons,
        ]
        return PruneDecision(cells, state, "\n".join(summary_lines))

    if reclaimed <= 0:
        # Report the pre-mutation ledger, as the incomplete no-op branch above does: after
        # `replace_analyzer_rules` reset each rule's `current` to the baseline-file total, the
        # post-prune state would overstate what a prior `check` had already lowered.
        message = f"Nothing to reclaim. {total_violations(previous)} still grandfathered."
    else:
        message = "\n".join(
            [
                f"Reclaimed {reclaimed} violations. Ceiling: {total_before} -> {total_after}.",
                *analyzer_notes,
                "Commit .ebpy/baseline.json together with the fix — the ceiling just came down.",
            ]
        )
    if incomplete_reasons:
        message = "\n".join(
            [
                message,
                "Some analyzers could not be measured; their ceilings were left unchanged:",
                *incomplete_reasons,
            ]
        )
    return PruneDecision(cells, state, message)


def run_prune(cwd: Path) -> str:
    """`freeze` pins whatever exists today, so running it a second time would
    grandfather violations added since. `prune` can only ever lower a cell to what
    still exists, which makes it safe to run after a ceiling has been frozen — provided
    both artifacts holding that ceiling are readable."""
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        raise CommandError(invalid_artifacts_message(artifacts))
    if artifacts.kind == "fresh":
        raise CommandError(NO_FROZEN_CEILING)
    previous = artifacts.ledger.state
    assert previous is not None

    # Compare with the baseline file, not the ledger: check may already have lowered
    # the ledger's current values, which would make every prune look like a no-op.
    decision = prune_measurement(previous, artifacts.cells, measure_repository(cwd))
    write_cells(cwd, decision.cells)
    write_state(cwd, decision.state)
    write_quality_file(cwd, decision.state)
    return decision.message
