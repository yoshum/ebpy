"""The measurement seam: one observation per analyzer, and how each is classified from tool output."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from ebpy import measurement
from ebpy.measurement import (
    Failed,
    Measured,
    Measurement,
    Unavailable,
    classify,
)
from ebpy.models import AnalysisMeasurement, UnattributedFinding
from ebpy.tools import ANALYZER_NAMES, ANALYZERS, ANALYZERS_BY_NAME, measure_repository
from ebpy.tools import mypy as mypy_tool
from ebpy.tools import ruff as ruff_tool
from ebpy.tools.mypy._runner import MypyFailedError, MypyInvalidOutputError, MypyNotFoundError
from ebpy.tools.ruff._runner import RuffFailedError, RuffInvalidOutputError, RuffNotFoundError


def test_each_capability_has_one_observation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ruff_result = AnalysisMeasurement(cells={})
    mypy_result = AnalysisMeasurement(cells={})
    monkeypatch.setattr(ruff_tool, "run_ruff_check", lambda _cwd: ruff_result)
    monkeypatch.setattr(mypy_tool, "run_mypy_check", lambda _cwd: mypy_result)

    result = measure_repository(tmp_path)

    assert result.analyzers["ruff"] == Measured(tool="ruff", value=ruff_result)
    assert result.analyzers["mypy"] == Measured(tool="mypy", value=mypy_result)


def test_mypy_is_measured_after_ruff_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fail_ruff(_cwd: Path) -> AnalysisMeasurement:
        calls.append("ruff")
        raise RuffFailedError("ruff check failed")

    def run_mypy(_cwd: Path) -> AnalysisMeasurement:
        calls.append("mypy")
        return AnalysisMeasurement(cells={"src/a.py": {"mypy:arg-type": 1}})

    monkeypatch.setattr(ruff_tool, "run_ruff_check", fail_ruff)
    monkeypatch.setattr(mypy_tool, "run_mypy_check", run_mypy)

    result = measure_repository(tmp_path)

    assert calls == ["ruff", "mypy"]
    assert result.analyzers["ruff"] == Failed(
        tool="ruff", failure_kind="execution-failed", detail="ruff check failed"
    )
    assert result.analyzers["mypy"] == Measured(
        tool="mypy", value=AnalysisMeasurement(cells={"src/a.py": {"mypy:arg-type": 1}})
    )


def test_a_failing_ruff_still_leaves_a_measured_mypy_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR #9's independence property: a failed analyzer must not discard the other's result."""

    def fail_ruff(_cwd: Path) -> AnalysisMeasurement:
        raise RuffFailedError("ruff check failed")

    monkeypatch.setattr(ruff_tool, "run_ruff_check", fail_ruff)
    monkeypatch.setattr(
        mypy_tool,
        "run_mypy_check",
        lambda _cwd: AnalysisMeasurement(cells={"a.py": {"mypy:arg-type": 1}}),
    )

    result = measure_repository(tmp_path)

    assert isinstance(result.analyzers["ruff"], Failed)
    assert result.analyzers["mypy"] == Measured(
        tool="mypy", value=AnalysisMeasurement(cells={"a.py": {"mypy:arg-type": 1}})
    )


def test_unavailable_tools_are_not_reported_as_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_ruff(_cwd: Path) -> AnalysisMeasurement:
        raise RuffNotFoundError("ruff is not installed here")

    def missing_mypy(_cwd: Path) -> AnalysisMeasurement:
        raise MypyNotFoundError("mypy is not installed here")

    monkeypatch.setattr(ruff_tool, "run_ruff_check", missing_ruff)
    monkeypatch.setattr(mypy_tool, "run_mypy_check", missing_mypy)

    result = measure_repository(tmp_path)

    assert result.analyzers["ruff"] == Unavailable(tool="ruff", detail="ruff is not installed here")
    assert result.analyzers["mypy"] == Unavailable(tool="mypy", detail="mypy is not installed here")


def test_mypy_failure_is_distinct_from_mypy_being_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ruff_result = AnalysisMeasurement(cells={})
    monkeypatch.setattr(ruff_tool, "run_ruff_check", lambda _cwd: ruff_result)

    def fail_mypy(_cwd: Path) -> AnalysisMeasurement:
        raise MypyFailedError("mypy failed (exit 2)")

    monkeypatch.setattr(mypy_tool, "run_mypy_check", fail_mypy)

    result = measure_repository(tmp_path)

    assert result.analyzers["mypy"] == Failed(
        tool="mypy", failure_kind="execution-failed", detail="mypy failed (exit 2)"
    )
    # A mypy failure must not skip or discard Ruff's own result — independence cuts both ways.
    assert result.analyzers["ruff"] == Measured(tool="ruff", value=ruff_result)


def test_invalid_mypy_output_is_a_distinct_failure_kind_from_execution_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MypyInvalidOutputError is a subclass of MypyFailedError and must be caught first,
    or every invalid-output failure would be misreported as a plain execution failure.
    """
    monkeypatch.setattr(ruff_tool, "run_ruff_check", lambda _cwd: AnalysisMeasurement(cells={}))

    def invalid_mypy(_cwd: Path) -> AnalysisMeasurement:
        raise MypyInvalidOutputError("mypy produced an unparseable error line")

    monkeypatch.setattr(mypy_tool, "run_mypy_check", invalid_mypy)

    result = measure_repository(tmp_path)

    assert result.analyzers["mypy"] == Failed(
        tool="mypy", failure_kind="invalid-output", detail="mypy produced an unparseable error line"
    )


def test_invalid_lint_output_is_distinct_from_tool_execution_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid_ruff(_cwd: Path) -> AnalysisMeasurement:
        raise RuffInvalidOutputError("ruff produced unparseable output")

    monkeypatch.setattr(ruff_tool, "run_ruff_check", invalid_ruff)
    monkeypatch.setattr(mypy_tool, "run_mypy_check", lambda _cwd: AnalysisMeasurement(cells={}))

    result = measure_repository(tmp_path)

    assert result.analyzers["ruff"] == Failed(
        tool="ruff",
        failure_kind="invalid-output",
        detail="ruff produced unparseable output",
    )


def test_measurement_rejects_an_invalid_analyzer_name_as_a_key() -> None:
    with pytest.raises(ValueError, match="Pylint"):
        Measurement(analyzers={"Pylint": Measured(tool="Pylint", value=AnalysisMeasurement(cells={}))})


def test_measurement_rejects_an_observation_whose_tool_disagrees_with_its_key() -> None:
    with pytest.raises(ValueError, match="ruff"):
        Measurement(analyzers={"ruff": Measured(tool="mypy", value=AnalysisMeasurement(cells={}))})


def test_measurement_rejects_a_rule_id_from_another_analyzers_namespace() -> None:
    stray = AnalysisMeasurement(cells={"a.py": {"mypy:arg-type": 1}})
    with pytest.raises(ValueError, match="mypy:arg-type"):
        Measurement(analyzers={"ruff": Measured(tool="ruff", value=stray)})


def test_measurement_freezes_the_analyzer_mapping_and_every_cell_mapping() -> None:
    analyzers: dict[str, Any] = {
        "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={"a.py": {"ruff:F401": 1}}))
    }
    result = Measurement(analyzers=analyzers)

    analyzers["ruff"] = Measured(tool="ruff", value=AnalysisMeasurement(cells={}))

    kept = cast("Measured[AnalysisMeasurement]", result.analyzers["ruff"])
    assert kept.value.cells["a.py"]["ruff:F401"] == 1
    with pytest.raises(TypeError):
        cast("Any", result.analyzers)["ruff"] = Measured(tool="ruff", value=AnalysisMeasurement(cells={}))
    with pytest.raises(TypeError):
        cast("Any", kept.value.cells["a.py"])["ruff:F401"] = 2


def test_classify_of_a_measured_observation_with_no_unattributed_findings_is_complete() -> None:
    assert classify(Measured(tool="ruff", value=AnalysisMeasurement(cells={}))) == "complete"


def test_classify_of_a_measured_observation_with_unattributed_findings_is_incomplete() -> None:
    measured = Measured(
        tool="ruff",
        value=AnalysisMeasurement(
            cells={}, unattributed=(UnattributedFinding(file="broken.py", line=1, message="boom"),)
        ),
    )
    assert classify(measured) == "incomplete"


def test_classify_of_an_unavailable_observation_is_unavailable() -> None:
    assert classify(Unavailable(tool="mypy", detail="not installed")) == "unavailable"


def test_classify_of_a_failed_observation_is_failed() -> None:
    assert classify(Failed(tool="mypy", failure_kind="execution-failed", detail="boom")) == "failed"


def test_classify_of_no_observation_at_all_is_no_runner() -> None:
    """A ceiling contract naming an analyzer this ebpy build has no runner for is its own
    status, kept apart from a tool that broke so callers can word the unfixable case.
    """
    assert classify(None) == "no-runner"


def test_analyzer_names_are_derived_from_the_registry() -> None:
    """The name list is the registry's keys, sorted, so the two cannot drift apart."""
    assert tuple(sorted(a.name for a in ANALYZERS)) == ANALYZER_NAMES
    assert set(ANALYZERS_BY_NAME) == set(ANALYZER_NAMES)


def test_measure_repository_produces_one_observation_per_registered_analyzer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every analyzer in the registry is attempted, and no other name appears."""
    monkeypatch.setattr(ruff_tool, "run_ruff_check", lambda _cwd: AnalysisMeasurement(cells={}))
    monkeypatch.setattr(mypy_tool, "run_mypy_check", lambda _cwd: AnalysisMeasurement(cells={}))

    result = measure_repository(tmp_path)

    assert set(result.analyzers) == set(ANALYZER_NAMES)


def test_two_different_failures_do_not_arrive_as_the_same_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason a tool refused is the whole value of being told it refused."""

    def failing(detail: str) -> Any:
        def raise_it(_cwd: Path) -> AnalysisMeasurement:
            raise RuffFailedError(
                "ruff check failed (exit 2)", detail=f"ruff check failed (exit 2):\n{detail}"
            )

        return raise_it

    monkeypatch.setattr(mypy_tool, "run_mypy_check", lambda _cwd: AnalysisMeasurement(cells={}))

    monkeypatch.setattr(ruff_tool, "run_ruff_check", failing("Cause: Failed to parse pyproject.toml"))
    parse_failure = measure_repository(tmp_path).analyzers["ruff"]
    monkeypatch.setattr(ruff_tool, "run_ruff_check", failing("Cause: Unknown rule selector `NOPE999`"))
    selector_failure = measure_repository(tmp_path).analyzers["ruff"]

    assert parse_failure != selector_failure
    assert "Failed to parse pyproject.toml" in cast("Failed", parse_failure).detail
    assert "Unknown rule selector" in cast("Failed", selector_failure).detail


def test_a_detail_keeps_every_line_the_tool_wrote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_it(_cwd: Path) -> AnalysisMeasurement:
        raise RuffFailedError(
            "head: first cause", detail="head:\n  Cause: first\n  Cause: deeper\n  detail line"
        )

    monkeypatch.setattr(ruff_tool, "run_ruff_check", raise_it)
    monkeypatch.setattr(mypy_tool, "run_mypy_check", lambda _cwd: AnalysisMeasurement(cells={}))

    ruff = cast("Failed", measure_repository(tmp_path).analyzers["ruff"])

    assert ruff.detail.splitlines() == ["head:", "  Cause: first", "  Cause: deeper", "  detail line"]
    # The runner chose the summary; it is not simply the detail's first line.
    assert ruff.summary == "head: first cause"


def test_a_runaway_detail_is_cut_and_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A truncated detail that looked complete would be a report claiming more than it holds."""
    flood = "\n".join(f"line {n}" for n in range(200))

    def raise_it(_cwd: Path) -> AnalysisMeasurement:
        raise RuffFailedError("flooded", detail=flood)

    monkeypatch.setattr(ruff_tool, "run_ruff_check", raise_it)
    monkeypatch.setattr(mypy_tool, "run_mypy_check", lambda _cwd: AnalysisMeasurement(cells={}))

    ruff = cast("Failed", measure_repository(tmp_path).analyzers["ruff"])

    assert ruff.detail.splitlines()[-1] == "... (truncated)"
    assert len(ruff.detail.splitlines()) == measurement.observation._DETAIL_LINES + 1


def test_an_observation_without_a_summary_falls_back_to_its_first_line() -> None:
    assert Unavailable(tool="mypy", detail="not installed\nsecond line").summary == "not installed"
    assert Failed(tool="ruff", failure_kind="execution-failed", detail="boom\nmore").summary == "boom"
