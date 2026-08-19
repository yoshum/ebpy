from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from ebpy import measurement
from ebpy.measurement import Failed, Measured, Unavailable, measure_repository
from ebpy.models import MYPY_COUNTER, LintMeasurement
from ebpy.mypy_runner import MypyFailedError, MypyNotFoundError
from ebpy.ruff_runner import RuffFailedError, RuffInvalidOutputError, RuffNotFoundError


def test_each_capability_has_one_observation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lint = LintMeasurement(cells={})
    monkeypatch.setattr(measurement, "run_ruff_check", lambda _cwd: lint)
    monkeypatch.setattr(measurement, "run_mypy_check", lambda _cwd: 0)

    result = measure_repository(tmp_path)

    assert result.lint == Measured(tool="ruff", value=lint)
    assert result.counters == {MYPY_COUNTER: Measured(tool="mypy", value=0)}


def test_mypy_is_measured_after_ruff_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_unavailable_tools_are_not_reported_as_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_measurement_copies_and_freezes_counter_observations() -> None:
    counters = {MYPY_COUNTER: Measured(tool="mypy", value=3)}
    result = measurement.Measurement(
        lint=Measured(tool="ruff", value=LintMeasurement(cells={})),
        counters=counters,
    )

    counters[MYPY_COUNTER] = Measured(tool="mypy", value=0)

    assert result.counters[MYPY_COUNTER] == Measured(tool="mypy", value=3)
    with pytest.raises(TypeError):
        cast(Any, result.counters)[MYPY_COUNTER] = Measured(tool="mypy", value=0)


def test_measurement_copies_and_deeply_freezes_lint_cells() -> None:
    cells = {"src/a.py": {"F401": 1}}
    result = LintMeasurement(cells=cells)

    cells["src/a.py"]["F401"] = 2

    assert result.cells["src/a.py"]["F401"] == 1
    with pytest.raises(TypeError):
        cast(Any, result.cells["src/a.py"])["F401"] = 2


def test_two_different_failures_do_not_arrive_as_the_same_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason a tool refused is the whole value of being told it refused."""

    def failing(detail: str) -> Any:
        def raise_it(_cwd: Path) -> LintMeasurement:
            raise RuffFailedError(
                "ruff check failed (exit 2)", detail=f"ruff check failed (exit 2):\n{detail}"
            )

        return raise_it

    monkeypatch.setattr(measurement, "run_mypy_check", lambda _cwd: 0)

    monkeypatch.setattr(measurement, "run_ruff_check", failing("Cause: Failed to parse pyproject.toml"))
    parse_failure = measure_repository(tmp_path).lint
    monkeypatch.setattr(measurement, "run_ruff_check", failing("Cause: Unknown rule selector `NOPE999`"))
    selector_failure = measure_repository(tmp_path).lint

    assert parse_failure != selector_failure
    assert "Failed to parse pyproject.toml" in cast(Failed, parse_failure).detail
    assert "Unknown rule selector" in cast(Failed, selector_failure).detail


def test_a_detail_keeps_every_line_the_tool_wrote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_it(_cwd: Path) -> LintMeasurement:
        raise RuffFailedError(
            "head: first cause", detail="head:\n  Cause: first\n  Cause: deeper\n  detail line"
        )

    monkeypatch.setattr(measurement, "run_ruff_check", raise_it)
    monkeypatch.setattr(measurement, "run_mypy_check", lambda _cwd: 0)

    lint = cast(Failed, measure_repository(tmp_path).lint)

    assert lint.detail.splitlines() == ["head:", "  Cause: first", "  Cause: deeper", "  detail line"]
    # The runner chose the summary; it is not simply the detail's first line.
    assert lint.summary == "head: first cause"


def test_a_runaway_detail_is_cut_and_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A truncated detail that looked complete would be a report claiming more than it holds."""
    flood = "\n".join(f"line {n}" for n in range(200))

    def raise_it(_cwd: Path) -> LintMeasurement:
        raise RuffFailedError("flooded", detail=flood)

    monkeypatch.setattr(measurement, "run_ruff_check", raise_it)
    monkeypatch.setattr(measurement, "run_mypy_check", lambda _cwd: 0)

    lint = cast(Failed, measure_repository(tmp_path).lint)

    assert lint.detail.splitlines()[-1] == "... (truncated)"
    assert len(lint.detail.splitlines()) == measurement._DETAIL_LINES + 1


def test_an_observation_without_a_summary_falls_back_to_its_first_line() -> None:
    assert Unavailable(tool="mypy", detail="not installed\nsecond line").summary == "not installed"
    assert Failed(tool="ruff", failure_kind="execution-failed", detail="boom\nmore").summary == "boom"
