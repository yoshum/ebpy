from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.commands import report as report_command
from ebpy.commands.report import run_report
from ebpy.decide.analysis_report import report_from_measurement
from ebpy.measurement import Failed, Measured, Measurement, Unavailable
from ebpy.models import AnalysisMeasurement
from ebpy.render.analysis_report import render_analysis_report


def test_report_keeps_contract_backlog_when_one_analyzer_fails() -> None:
    """A failed contract analyzer falls back to its baseline cells; the report still builds."""
    measurement = Measurement(
        analyzers={
            "ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff check failed"),
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={}, files_with_findings=0)),
        }
    )

    report = report_from_measurement({"src/a.py": {"ruff:F401": 2}}, ("ruff", "mypy"), measurement)

    # ruff failed → falls back to its baseline cells unchanged
    assert report.backlog_total == 2
    rendered = render_analysis_report(report)
    assert "ruff did not run" in rendered
    assert "ruff check failed" in rendered


def test_report_names_why_an_analyzer_was_not_measured() -> None:
    """An unavailable analyzer shows its detail, not a zero or a blank."""
    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed here"),
        }
    )

    report = report_from_measurement({}, ("ruff", "mypy"), measurement)

    _, mypy_summary = next((name, s) for name, s in report.analyzers if name == "mypy")
    assert mypy_summary.findings is None
    assert mypy_summary.failure == "mypy is not installed here"
    rendered = render_analysis_report(report)
    assert "not measured" in rendered
    assert "mypy is not installed here" in rendered


def test_report_compares_measured_cells_with_the_ceiling() -> None:
    """Excess above the per-file ceiling is counted as new; what remains is the backlog."""
    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 3}}, files_with_findings=1),
            ),
            "mypy": Failed(tool="mypy", failure_kind="execution-failed", detail="bad config"),
        }
    )

    report = report_from_measurement({"src/a.py": {"ruff:F401": 2}}, ("ruff", "mypy"), measurement)

    assert report.new_total == 1
    assert report.backlog_total == 2
    _, mypy_summary = next((name, s) for name, s in report.analyzers if name == "mypy")
    assert mypy_summary.failure == "bad config"


def test_report_shell_gathers_once_then_renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []
    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
        }
    )

    def gather(cwd: Path) -> Measurement:
        calls.append(cwd)
        return measurement

    monkeypatch.setattr(report_command, "measure_repository", gather)

    assert "# Analysis report" in run_report(tmp_path, as_json=False)
    assert calls == [tmp_path]


def test_a_failed_analyzer_is_named_rather_than_rendered_as_zero() -> None:
    """A failed analyzer shows 'not measured', not a zero count."""
    report = report_from_measurement(
        {},
        ("mypy",),
        Measurement(
            analyzers={
                "mypy": Failed(
                    tool="mypy",
                    failure_kind="execution-failed",
                    detail="mypy failed (exit 2): mypy.ini: Unrecognized option",
                )
            }
        ),
    )

    _, mypy_summary = next((name, s) for name, s in report.analyzers if name == "mypy")
    assert mypy_summary.findings is None
    assert mypy_summary.failure == "mypy failed (exit 2): mypy.ini: Unrecognized option"
    rendered = render_analysis_report(report)
    assert "not measured" in rendered
    assert "mypy did not run" in rendered
    assert "mypy failed (exit 2): mypy.ini: Unrecognized option" in rendered


def test_a_measured_analyzer_carries_no_failure() -> None:
    """A successfully measured analyzer has failure=None."""
    report = report_from_measurement(
        {},
        ("mypy",),
        Measurement(
            analyzers={
                "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
            }
        ),
    )

    payload = report.to_dict()
    assert payload["analyzers"]["mypy"]["failure"] is None
    rendered = render_analysis_report(report)
    assert "mypy did not run" not in rendered


def test_report_exits_zero_when_every_analyzer_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_report exits 0 even when every analyzer failed; only invalid artifacts raise."""
    measurement = Measurement(
        analyzers={
            "ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff gone"),
            "mypy": Failed(tool="mypy", failure_kind="execution-failed", detail="mypy gone"),
        }
    )

    monkeypatch.setattr(report_command, "measure_repository", lambda _cwd: measurement)

    # run_report returns a string (not raises) for any non-invalid artifact pair
    result = run_report(tmp_path, as_json=False)
    assert isinstance(result, str)
    assert "# Analysis report" in result
