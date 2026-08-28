"""`report`: gathering measurements once, comparing with the ceiling, naming unmeasured analyzers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from ebpy.commands import report as report_command
from ebpy.commands.report import run_report
from ebpy.decide.analysis_report import report_from_measurement
from ebpy.errors import CommandError
from ebpy.measurement import Failed, Measured, Measurement, Unavailable
from ebpy.models import AnalysisMeasurement, CellCounts, RuleBaseline, State
from ebpy.render.analysis_report import render_analysis_report
from ebpy.store.baseline import write_cells
from ebpy.store.state import write_state

if TYPE_CHECKING:
    from pathlib import Path


def _write_frozen_pair(
    cwd: Path,
    *,
    frozen_analyzers: tuple[str, ...],
    cells: CellCounts,
    rules: dict[str, RuleBaseline] | None = None,
) -> None:
    # A pyproject.toml so language detection evidences Python here — without it, an
    # unconfigured repository has no analyzer scope no matter what the ledger records.
    (cwd / "pyproject.toml").touch()
    write_cells(cwd, cells)
    state = State(
        frozen_analyzers=frozen_analyzers, rules=rules or {}, frozen_at="2026-08-19T00:00:00Z", phase="drain"
    )
    write_state(cwd, state)


def test_report_keeps_contract_backlog_when_one_analyzer_fails() -> None:
    """A failed contract analyzer falls back to its baseline cells; the report still builds."""
    measurement = Measurement(
        analyzers={
            "ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff check failed"),
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
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
                value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 3}}),
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
    (tmp_path / "pyproject.toml").touch()
    calls: list[Path] = []
    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
        }
    )

    def gather(cwd: Path, _scope: tuple[str, ...]) -> Measurement:
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
    (tmp_path / "pyproject.toml").touch()
    measurement = Measurement(
        analyzers={
            "ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff gone"),
            "mypy": Failed(tool="mypy", failure_kind="execution-failed", detail="mypy gone"),
        }
    )

    monkeypatch.setattr(report_command, "measure_repository", lambda _cwd, _scope: measurement)

    # run_report returns a string (not raises) for any non-invalid artifact pair
    result = run_report(tmp_path, as_json=False)
    assert isinstance(result, str)
    assert "# Analysis report" in result


def test_report_does_not_refuse_when_the_contract_and_the_scope_disagree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report is the window a reader opens because something is wrong; it stays open."""
    # config.json declares only ruff while mypy is also frozen — the `declared ^ frozen`
    # branch of ScopeDecision.scope_mismatches, a genuine disagreement rather than one
    # that only looks like it because the analyzer has no runner in this build.
    _write_frozen_pair(tmp_path, frozen_analyzers=("ruff", "mypy"), cells={})
    (tmp_path / ".ebpy" / "config.json").write_text(
        json.dumps({"version": 1, "analyzers": ["ruff"]}), encoding="utf-8"
    )
    monkeypatch.setattr(report_command, "measure_repository", lambda _cwd, _scope: Measurement({}))

    output = json.loads(run_report(tmp_path, as_json=True))

    assert output["analyzers"]["mypy"]["status"] == "scope-mismatch"


def test_report_refuses_on_a_fresh_repository_with_nothing_to_measure(tmp_path: Path) -> None:
    """With no contract and no analyzer there is no standing for the report to show."""
    with pytest.raises(CommandError):
        run_report(tmp_path, as_json=False)
