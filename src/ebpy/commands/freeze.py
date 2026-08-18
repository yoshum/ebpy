"""P2: pin today's violations as the ceiling.

Running it a second time is refused: that would grandfather everything added
since, which is the one thing the baseline exists to prevent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ..baseline import rule_totals, write_cells
from ..ceiling_artifacts import CeilingArtifacts, invalid_artifacts_message, read_ceiling_artifacts
from ..errors import CommandError
from ..models import MYPY_COUNTER, State
from ..mypy_runner import run_mypy_error_count
from ..quality_file import write_quality_file
from ..ruff_runner import RuffResult, run_ruff_check
from ..state import (
    BaselineMode,
    apply_rule_counts,
    empty_state,
    set_counter,
    with_phase,
    write_state,
)

_UNATTRIBUTED_SHOWN = 5


def _unattributed_report(result: RuffResult) -> list[str]:
    """Syntax errors are not rule violations the baseline can grandfather: a file that
    does not parse is invisible to every rule, so recording a count for it would be a
    lie. Naming the files turns a mystery into a task."""
    if not result.unattributed:
        return []
    files = sorted({item.file for item in result.unattributed})
    samples = [
        f"  {item.file}:{item.line}  {item.message}" for item in result.unattributed[:_UNATTRIBUTED_SHOWN]
    ]
    more = len(result.unattributed) - len(samples)
    return [
        "",
        f"WARNING: {len(result.unattributed)} syntax error(s) in {len(files)} file(s) — "
        "Ruff could not lint them:",
        *samples,
        *([f"  + {more} more"] if more > 0 else []),
        "These cannot be grandfathered: a file that does not parse has no violations to count.",
        "Fix them, then re-run freeze so those files enter the baseline.",
    ]


def _already_frozen(artifacts: CeilingArtifacts) -> str:
    state = artifacts.ledger.state
    assert state is not None and state.frozen_at is not None
    return "\n".join(
        [
            f"Already frozen at {state.frozen_at}.",
            "Freezing again would grandfather everything added since, which is the one thing the",
            "baseline exists to prevent. To reclaim cells you have fixed, run `ebpy prune`.",
            "To deliberately replace the contract, re-run with --force.",
        ]
    )


def _previous_state(artifacts: CeilingArtifacts, force: bool) -> State:
    """Choose metadata to preserve; a forced recovery trusts no invalid artifact."""
    if artifacts.kind == "invalid":
        return empty_state()
    state = artifacts.ledger.state or empty_state()
    if force:
        # `--force` pins a complete new contract. Keeping an unmeasured old counter or
        # rule would make the result depend on the contract it claims to replace.
        state.rules = {}
        state.counters = {}
    return state


def run_freeze(cwd: Path, force: bool) -> str:
    artifacts = read_ceiling_artifacts(cwd)
    if not force:
        # Read before measuring: a repository that must not be frozen must not have its
        # ceiling raised by the run that discovers it.
        if artifacts.kind == "invalid":
            raise CommandError(invalid_artifacts_message(artifacts))
        if artifacts.kind == "frozen":
            raise CommandError(_already_frozen(artifacts))

    previous = _previous_state(artifacts, force)

    result = run_ruff_check(cwd)
    write_cells(cwd, result.cells)

    mode: BaselineMode = "rebaseline" if force else "freeze"
    counts = rule_totals(result.cells)
    state: State = apply_rule_counts(previous, counts, mode)
    mypy_errors = run_mypy_error_count(cwd)
    if mypy_errors is not None:
        state = set_counter(state, MYPY_COUNTER, mypy_errors, mode)
    state.frozen_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    state = with_phase(state, "drain")
    write_state(cwd, state)
    write_quality_file(cwd, state)

    backlog = sum(counts.values())
    mypy_line = (
        f"{mypy_errors} mypy errors are ratcheted as a counter — they have no per-file suppression."
        if mypy_errors is not None
        else "mypy did not run, so no type-error ceiling was recorded."
    )
    return "\n".join(
        [
            f"Baseline pinned: {backlog} violations across {len(counts)} rules are now grandfathered.",
            mypy_line,
            "New code is held to the full rule set from here.",
            *_unattributed_report(result),
            "",
            "Commit .ebpy/baseline.json, .ebpy/state.json and QUALITY.md.",
            "Next: `ebpy next` ranks what to drain first.",
        ]
    )
