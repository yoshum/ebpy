"""After a fix, reclaim the ceiling you earned. The only way the ceiling comes down."""

from __future__ import annotations

from pathlib import Path

from ..baseline import prune_cells, read_cells, read_suppression_total, write_cells
from ..mypy_runner import run_mypy_error_count
from ..quality_file import write_quality_file
from ..ruff_runner import rule_totals, run_ruff_check
from ..state import (
    MYPY_COUNTER,
    apply_rule_counts,
    empty_state,
    read_state,
    set_counter,
    total_violations,
    write_state,
)


def run_prune(cwd: Path) -> str:
    """`freeze` pins whatever exists today, so running it a second time would
    grandfather violations added since. `prune` can only ever lower a cell to what
    still exists, which makes it safe to run at any point."""
    # Measured against the baseline FILE, not the ledger: a `check` run since the fix
    # has already lowered the ledger, so comparing that would report every prune as a
    # no-op.
    before = read_suppression_total(cwd)
    result = run_ruff_check(cwd)
    pruned = prune_cells(read_cells(cwd), result.cells)
    write_cells(cwd, pruned)
    after = sum(count for rules in pruned.values() for count in rules.values())

    state = apply_rule_counts(read_state(cwd) or empty_state(), rule_totals(pruned), "freeze")
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
