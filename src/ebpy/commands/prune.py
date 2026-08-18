"""After a fix, reclaim the ceiling you earned. The only way the ceiling comes down."""

from __future__ import annotations

from pathlib import Path

from ..baseline import prune_cells, rule_totals, write_cells
from ..ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..errors import CommandError
from ..models import MYPY_COUNTER
from ..mypy_runner import run_mypy_error_count
from ..quality_file import write_quality_file
from ..ruff_runner import run_ruff_check
from ..state import (
    apply_rule_counts,
    set_counter,
    total_violations,
    write_state,
)

NO_FROZEN_CEILING = "\n".join(
    [
        "Refusing to prune: no frozen ceiling is recorded yet.",
        "Run `ebpy freeze` first; prune can only lower a ceiling that already exists.",
    ]
)


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

    # Measured against the baseline FILE, not the ledger: a `check` run since the fix
    # has already lowered the ledger, so comparing that would report every prune as a
    # no-op.
    baseline = artifacts.cells
    before = sum(count for rules in baseline.values() for count in rules.values())
    result = run_ruff_check(cwd)
    pruned = prune_cells(baseline, result.cells)
    write_cells(cwd, pruned)
    after = sum(count for rules in pruned.values() for count in rules.values())

    state = apply_rule_counts(previous, rule_totals(pruned), "freeze")
    mypy_errors = run_mypy_error_count(cwd)
    if mypy_errors is not None:
        state = set_counter(state, MYPY_COUNTER, mypy_errors, "freeze")
    write_state(cwd, state)
    write_quality_file(cwd, state)

    reclaimed = before - after
    if reclaimed <= 0:
        return f"Nothing to reclaim. {total_violations(state)} still grandfathered."
    return "\n".join(
        [
            f"Reclaimed {reclaimed} violations. Ceiling: {before} -> {after}.",
            "Commit .ebpy/baseline.json together with the fix — the ceiling just came down.",
        ]
    )
