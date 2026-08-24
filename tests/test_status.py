"""`ebpy status`: the current backlog, the frozen analyzer roster, and no regression count."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ebpy.commands.status import run_status
from ebpy.models import RuleBaseline
from ebpy.store.baseline import write_cells
from ebpy.store.state import empty_state, write_state

if TYPE_CHECKING:
    from pathlib import Path


def _frozen_state(cwd: Path, rules: dict[str, int], analyzers: tuple[str, ...]) -> None:
    state = empty_state()
    state.rules = {
        name: RuleBaseline(baseline=count, current=count, status="enforced" if count == 0 else "draining")
        for name, count in rules.items()
    }
    state.frozen_analyzers = analyzers
    state.frozen_at = "2026-08-19T00:00:00Z"
    state.phase = "drain"
    write_state(cwd, state)


def test_status_lists_the_frozen_analyzers_and_no_regression_count(tmp_path: Path) -> None:
    """Status lists the frozen analyzers and reports no regression count anywhere.

    The roster line names every analyzer the ledger holds a ceiling for, and no line in
    the output reports a regression count anywhere — state v2 stores only held counts, so a
    regression is structurally unrepresentable and the deleted verdict line must not have
    grown back next to the new one.
    """
    write_cells(tmp_path, {"src/app.py": {"ruff:F401": 2, "mypy:arg-type": 1}})
    _frozen_state(tmp_path, {"ruff:F401": 2, "mypy:arg-type": 1}, ("mypy", "ruff"))

    output = run_status(tmp_path, False)

    assert "analyzers  mypy, ruff" in output
    assert "regressed" not in output


def test_status_reports_none_for_an_empty_analyzer_roster(tmp_path: Path) -> None:
    write_state(tmp_path, empty_state())

    output = run_status(tmp_path, False)

    assert "analyzers  none" in output
