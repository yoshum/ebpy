from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.baseline import write_cells
from ebpy.commands import check as check_command
from ebpy.commands.check import check_measurement, run_check
from ebpy.measurement import Failed, Measured, Measurement, Unavailable
from ebpy.models import MYPY_COUNTER, Counter, LintMeasurement
from ebpy.state import apply_rule_counts, empty_state, write_state


def frozen_state(cwd: Path) -> None:
    state = apply_rule_counts(empty_state(), {"F401": 1}, "freeze")
    state.frozen_at = "2026-08-19T00:00:00Z"
    state.phase = "drain"
    write_state(cwd, state)


def test_failed_lint_produces_no_state_to_persist() -> None:
    previous = empty_state()
    measurement = Measurement(
        lint=Failed(tool="ruff", failure_kind="execution-failed", detail="ruff failed"),
        counters={MYPY_COUNTER: Measured(tool="mypy", value=3)},
    )

    decision = check_measurement(previous, {}, measurement)

    assert not decision.result.ok
    assert decision.result.message == "ruff failed"
    assert decision.state is None
    assert previous.counters == {}


def test_check_updates_only_measured_counters() -> None:
    previous = apply_rule_counts(empty_state(), {"F401": 1}, "freeze")
    previous.counters = {MYPY_COUNTER: Counter(baseline=4, current=4)}
    measurement = Measurement(
        lint=Measured(tool="ruff", value=LintMeasurement(cells={"src/a.py": {"F401": 1}})),
        counters={MYPY_COUNTER: Unavailable(tool="mypy", detail="mypy is not installed")},
    )

    decision = check_measurement(previous, {"src/a.py": {"F401": 1}}, measurement)

    assert decision.result.ok
    assert decision.state is not None
    assert decision.state.counters[MYPY_COUNTER] == Counter(baseline=4, current=4)
    assert previous.rules["F401"].current == 1


def test_check_rejects_cells_beyond_the_ceiling() -> None:
    previous = apply_rule_counts(empty_state(), {"F401": 1}, "freeze")
    measurement = Measurement(
        lint=Measured(tool="ruff", value=LintMeasurement(cells={"src/a.py": {"F401": 2}})),
        counters={MYPY_COUNTER: Measured(tool="mypy", value=0)},
    )

    decision = check_measurement(previous, {"src/a.py": {"F401": 1}}, measurement)

    assert not decision.result.ok
    assert "1 violation(s) beyond the ceiling" in decision.result.message
    assert decision.state is not None
    assert decision.state.rules["F401"].current == 1
    assert decision.state.counters[MYPY_COUNTER].current == 0


def test_check_shell_does_not_write_after_lint_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_cells(tmp_path, {"src/a.py": {"F401": 1}})
    frozen_state(tmp_path)
    measurement = Measurement(
        lint=Failed(tool="ruff", failure_kind="execution-failed", detail="ruff failed"),
        counters={MYPY_COUNTER: Measured(tool="mypy", value=0)},
    )
    writes: list[str] = []
    monkeypatch.setattr(check_command, "measure_repository", lambda _cwd: measurement)
    monkeypatch.setattr(check_command, "write_state", lambda _cwd, _state: writes.append("state"))
    monkeypatch.setattr(check_command, "write_quality_file", lambda _cwd, _state: writes.append("quality"))

    result = run_check(tmp_path, write=True)

    assert not result.ok
    assert writes == []
