from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.commands import report as report_command
from ebpy.commands.report import report_from_measurement, run_report
from ebpy.measurement import Failed, Measured, Measurement, Unavailable
from ebpy.models import MYPY_COUNTER, AnalysisMeasurement
from ebpy.render.lint_report import render_lint_report


def test_report_keeps_mypy_when_lint_fails() -> None:
    measurement = Measurement(
        lint=Failed(tool="ruff", failure_kind="execution-failed", detail="ruff check failed"),
        counters={MYPY_COUNTER: Measured(tool="mypy", value=3)},
    )

    report = report_from_measurement({"src/a.py": {"F401": 2}}, measurement)

    assert report.lint_failure == "ruff check failed"
    assert report.backlog_total == 2
    assert report.mypy_errors == 3


def test_report_names_why_mypy_was_not_measured() -> None:
    measurement = Measurement(
        lint=Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
        counters={MYPY_COUNTER: Unavailable(tool="mypy", detail="mypy is not installed here")},
    )

    report = report_from_measurement({}, measurement)

    assert report.mypy_errors is None
    assert report.mypy_failure == "mypy is not installed here"
    rendered = render_lint_report(report)
    assert "- mypy errors: **not measured**" in rendered
    assert "> **mypy did not run**\n> mypy is not installed here" in rendered
    assert report.to_dict()["mypyFailure"] == "mypy is not installed here"


def test_report_compares_measured_lint_with_the_ceiling() -> None:
    measurement = Measurement(
        lint=Measured(
            tool="ruff",
            value=AnalysisMeasurement(cells={"src/a.py": {"F401": 3}}, files_with_findings=1),
        ),
        counters={MYPY_COUNTER: Failed(tool="mypy", failure_kind="execution-failed", detail="bad config")},
    )

    report = report_from_measurement({"src/a.py": {"F401": 2}}, measurement)

    assert report.new_total == 1
    assert report.backlog_total == 2
    assert report.files_with_findings == 1
    assert report.mypy_failure == "bad config"


def test_report_shell_gathers_once_then_renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []
    measurement = Measurement(
        lint=Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
        counters={MYPY_COUNTER: Measured(tool="mypy", value=0)},
    )

    def gather(cwd: Path) -> Measurement:
        calls.append(cwd)
        return measurement

    monkeypatch.setattr(report_command, "measure_repository", gather)

    assert "# Lint report" in run_report(tmp_path, as_json=False)
    assert calls == [tmp_path]


def test_a_failed_type_check_is_named_rather_than_rendered_as_zero() -> None:
    report = report_from_measurement(
        {},
        Measurement(
            lint=Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            counters={
                MYPY_COUNTER: Failed(
                    tool="mypy",
                    failure_kind="execution-failed",
                    detail="mypy failed (exit 2): mypy.ini: Unrecognized option",
                )
            },
        ),
    )

    assert report.mypy_errors is None
    assert report.to_dict()["mypyFailure"] == "mypy failed (exit 2): mypy.ini: Unrecognized option"
    # The bullet stays a bullet; the tool's own words go where every line of them fits.
    rendered = render_lint_report(report)
    assert "- mypy errors: **not measured**" in rendered
    assert "> **mypy did not run**\n> mypy failed (exit 2): mypy.ini: Unrecognized option" in rendered


def test_a_measured_type_check_carries_no_failure() -> None:
    report = report_from_measurement(
        {},
        Measurement(
            lint=Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            counters={MYPY_COUNTER: Measured(tool="mypy", value=3)},
        ),
    )

    assert report.to_dict()["mypyFailure"] is None
    assert "mypy errors: **3**" in render_lint_report(report)
