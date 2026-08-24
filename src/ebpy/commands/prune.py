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
    output_parts: list[CellCounts] = []
    analyzer_notes: list[str] = []
    incomplete_reasons: list[str] = []
    total_before = 0
    total_after = 0

    for analyzer in sorted(previous.frozen_analyzers):
        observation = measurement.analyzers.get(analyzer)
        status = classify(observation)
        baseline_cells = cells_for(baseline, analyzer)
        baseline_total = finding_total(baseline_cells)

        if status == "complete":
            assert isinstance(observation, Measured)
            current_cells = cells_for(observation.value.cells, analyzer)
            pruned = prune_cells(baseline_cells, current_cells)
            pruned_total = finding_total(pruned)
            reclaimed = baseline_total - pruned_total
            total_before += baseline_total
            total_after += pruned_total
            output_parts.append(pruned)
            # A rule whose findings are all gone must leave the namespace so the ledger stops
            # naming a ceiling the baseline file no longer carries; the helper's use of
            # `replace_analyzer_rules` (not a rule-by-rule lowering) is what drops it.
            state = align_analyzer_rules_to_cells(state, pruned, analyzer)
            analyzer_notes.append(_analyzer_note(analyzer, reclaimed, baseline_total, pruned_total))
        else:
            # A ceiling nobody re-measured cannot be lowered.
            output_parts.append(baseline_cells)
            total_before += baseline_total
            total_after += baseline_total
            incomplete_reasons.append(
                f"  {analyzer}: not measured — {_carry_reason(analyzer, status, observation)}"
            )
            analyzer_notes.append(f"  {analyzer}: {baseline_total} (not measured)")

    cells = merge_cells(output_parts)
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
