from __future__ import annotations

from pathlib import Path

import pytest

from ebpy import measurement
from ebpy.measurement import Failed, Measured, Unavailable, measure_repository
from ebpy.models import MYPY_COUNTER, LintMeasurement
from ebpy.mypy_runner import MypyFailedError, MypyNotFoundError
from ebpy.ruff_runner import RuffFailedError, RuffInvalidOutputError, RuffNotFoundError


def test_each_capability_has_one_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lint = LintMeasurement(cells={})
    monkeypatch.setattr(measurement, "run_ruff_check", lambda _cwd: lint)
    monkeypatch.setattr(measurement, "run_mypy_check", lambda _cwd: 0)

    result = measure_repository(tmp_path)

    assert result.lint == Measured(tool="ruff", value=lint)
    assert result.counters == {MYPY_COUNTER: Measured(tool="mypy", value=0)}


def test_mypy_is_measured_after_ruff_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fail_ruff(_cwd: Path) -> LintMeasurement:
        calls.append("ruff")
        raise RuffFailedError("ruff check failed")

    def run_mypy(_cwd: Path) -> int:
        calls.append("mypy")
        return 3

    monkeypatch.setattr(measurement, "run_ruff_check", fail_ruff)
    monkeypatch.setattr(measurement, "run_mypy_check", run_mypy)

    result = measure_repository(tmp_path)

    assert calls == ["ruff", "mypy"]
    assert result.lint == Failed(tool="ruff", failure_kind="execution-failed", detail="ruff check failed")
    assert result.counters[MYPY_COUNTER] == Measured(tool="mypy", value=3)


def test_unavailable_tools_are_not_reported_as_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing_ruff(_cwd: Path) -> LintMeasurement:
        raise RuffNotFoundError("ruff is not installed here")

    def missing_mypy(_cwd: Path) -> int:
        raise MypyNotFoundError("mypy is not installed here")

    monkeypatch.setattr(measurement, "run_ruff_check", missing_ruff)
    monkeypatch.setattr(measurement, "run_mypy_check", missing_mypy)

    result = measure_repository(tmp_path)

    assert result.lint == Unavailable(tool="ruff", detail="ruff is not installed here")
    assert result.counters[MYPY_COUNTER] == Unavailable(tool="mypy", detail="mypy is not installed here")


def test_mypy_failure_is_distinct_from_mypy_being_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(measurement, "run_ruff_check", lambda _cwd: LintMeasurement(cells={}))

    def fail_mypy(_cwd: Path) -> int:
        raise MypyFailedError("mypy failed (exit 2)")

    monkeypatch.setattr(measurement, "run_mypy_check", fail_mypy)

    result = measure_repository(tmp_path)

    assert result.counters[MYPY_COUNTER] == Failed(
        tool="mypy", failure_kind="execution-failed", detail="mypy failed (exit 2)"
    )


def test_invalid_lint_output_is_distinct_from_tool_execution_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid_ruff(_cwd: Path) -> LintMeasurement:
        raise RuffInvalidOutputError("ruff produced unparseable output")

    monkeypatch.setattr(measurement, "run_ruff_check", invalid_ruff)
    monkeypatch.setattr(measurement, "run_mypy_check", lambda _cwd: 0)

    result = measure_repository(tmp_path)

    assert result.lint == Failed(
        tool="ruff",
        failure_kind="invalid-output",
        detail="ruff produced unparseable output",
    )


def test_the_known_counter_cannot_be_omitted() -> None:
    with pytest.raises(ValueError, match=MYPY_COUNTER):
        measurement.Measurement(
            lint=Measured(tool="ruff", value=LintMeasurement(cells={})),
            counters={},
        )
