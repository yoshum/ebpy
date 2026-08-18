"""What `prune` refuses.

`prune` is documented as safe to run at any point, because it can only ever
lower a cell. That claim holds only for the cells clamped by the baseline file;
the ceilings for plain counters live in the ledger and have nothing to clamp
against, so a prune without a ledger would pin today's counts instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.baseline import BASELINE_FILE, baseline_path, write_cells
from ebpy.commands.prune import prune_measurement, run_prune
from ebpy.errors import CommandError
from ebpy.measurement import Failed, Measured, Measurement, Unavailable
from ebpy.models import MYPY_COUNTER, Counter, LintMeasurement
from ebpy.state import apply_rule_counts, empty_state, state_path, write_state


def test_prune_refuses_when_the_ledger_is_missing(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"F401": 1}})
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")

    with pytest.raises(CommandError, match=r"state\.json"):
        run_prune(tmp_path)

    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before
    assert not state_path(tmp_path).exists()


def test_prune_before_the_first_freeze_writes_nothing(tmp_path: Path) -> None:
    """`diagnose --write` and `log` both create a valid ledger before freeze. Its mere
    existence must not let prune create `{}`, which freeze would mistake for a ceiling
    pinned on a clean tree."""
    write_state(tmp_path, empty_state())
    state_before = state_path(tmp_path).read_text(encoding="utf-8")

    with pytest.raises(CommandError, match="freeze"):
        run_prune(tmp_path)

    assert not baseline_path(tmp_path).exists()
    assert state_path(tmp_path).read_text(encoding="utf-8") == state_before


def test_failed_lint_cannot_build_a_pruned_contract() -> None:
    previous = apply_rule_counts(empty_state(), {"F401": 2}, "freeze")
    measurement = Measurement(
        lint=Failed(tool="ruff", failure_kind="execution-failed", detail="ruff failed"),
        counters={MYPY_COUNTER: Measured(tool="mypy", value=1)},
    )

    with pytest.raises(CommandError, match="ruff failed"):
        prune_measurement(previous, {"src/a.py": {"F401": 2}}, measurement)

    assert previous.rules["F401"].current == 2
    assert previous.counters == {}


def test_prune_lowers_cells_and_measured_counters() -> None:
    previous = apply_rule_counts(empty_state(), {"F401": 2}, "freeze")
    previous.counters = {MYPY_COUNTER: Counter(baseline=4, current=4)}
    measurement = Measurement(
        lint=Measured(tool="ruff", value=LintMeasurement(cells={"src/a.py": {"F401": 1}})),
        counters={MYPY_COUNTER: Measured(tool="mypy", value=2)},
    )

    decision = prune_measurement(previous, {"src/a.py": {"F401": 2}}, measurement)

    assert decision.cells == {"src/a.py": {"F401": 1}}
    assert decision.state.rules["F401"].baseline == 1
    assert decision.state.counters[MYPY_COUNTER] == Counter(baseline=2, current=2)
    assert "Ceiling: 2 -> 1" in decision.message
    assert previous.rules["F401"].baseline == 2
    assert previous.counters[MYPY_COUNTER].baseline == 4


def test_prune_leaves_an_unmeasured_counter_unchanged() -> None:
    previous = apply_rule_counts(empty_state(), {}, "freeze")
    previous.counters = {MYPY_COUNTER: Counter(baseline=4, current=4)}
    measurement = Measurement(
        lint=Measured(tool="ruff", value=LintMeasurement(cells={})),
        counters={MYPY_COUNTER: Unavailable(tool="mypy", detail="mypy is not installed")},
    )

    decision = prune_measurement(previous, {}, measurement)

    assert decision.state.counters[MYPY_COUNTER] == Counter(baseline=4, current=4)
