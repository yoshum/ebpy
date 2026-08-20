"""After a fix, reclaim the ceiling you earned. The only way the ceiling comes down."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..errors import CommandError
from ..measurement import Measured, Measurement, measure_repository
from ..models import MYPY_COUNTER, CellCounts, State
from ..persist.baseline import prune_cells, rule_totals, write_cells
from ..persist.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..persist.state import (
    apply_rule_counts,
    copy_state,
    set_counter,
    total_violations,
    write_state,
)
from ..quality_file import write_quality_file

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


def prune_measurement(
    previous: State,
    baseline: CellCounts,
    measurement: Measurement,
) -> PruneDecision:
    """Lower one complete ceiling contract from measured facts without writing it."""
    lint = measurement.lint
    if not isinstance(lint, Measured):
        raise CommandError(lint.detail)

    before = sum(count for rules in baseline.values() for count in rules.values())
    pruned = prune_cells(baseline, lint.value.cells)
    after = sum(count for rules in pruned.values() for count in rules.values())

    state = apply_rule_counts(copy_state(previous), rule_totals(pruned), "freeze")
    mypy = measurement.counters[MYPY_COUNTER]
    if isinstance(mypy, Measured):
        state = set_counter(state, MYPY_COUNTER, mypy.value, "freeze")
        mypy_note = None
    elif MYPY_COUNTER in previous.counters:
        mypy_note = (
            f"{MYPY_COUNTER} was not measured; its existing ceiling was left unchanged: {mypy.summary}"
        )
    else:
        mypy_note = f"{MYPY_COUNTER} was not measured; no type-error ceiling was recorded: {mypy.summary}"

    reclaimed = before - after
    summary = (
        f"Nothing to reclaim. {total_violations(state)} still grandfathered."
        if reclaimed <= 0
        else "\n".join(
            [
                f"Reclaimed {reclaimed} violations. Ceiling: {before} -> {after}.",
                "Commit .ebpy/baseline.json together with the fix — the ceiling just came down.",
            ]
        )
    )
    message = "\n".join([summary, *([mypy_note] if mypy_note is not None else [])])
    return PruneDecision(pruned, state, message)


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
