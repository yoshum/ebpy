from __future__ import annotations

from ebpy.analysis_report import (
    area_of,
    matrix_from_cells,
    report_from_measurement,
)
from ebpy.measurement import Failed, Measured, Measurement, Unavailable
from ebpy.models import AnalysisMeasurement, UnattributedFinding
from ebpy.render.analysis_report import render_analysis_report

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ruff_measurement(cells: dict[str, dict[str, int]], files: int = 0) -> Measurement:
    return Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells=cells, files_with_findings=files))
        }
    )


# ---------------------------------------------------------------------------
# area_of / matrix_from_cells (unchanged primitives)
# ---------------------------------------------------------------------------


def test_a_root_file_belongs_to_a_named_area_not_an_empty_one() -> None:
    assert area_of("setup.py") == "(root)"
    assert area_of("src/pkg/a.py") == "src"


def test_the_matrix_folds_files_up_into_their_area() -> None:
    # Rule keys are namespaced in the new model; folding by area still works the same way.
    matrix = matrix_from_cells(
        {
            "src/a.py": {"ruff:E501": 2},
            "src/b.py": {"ruff:E501": 1},
            "tests/c.py": {"ruff:F401": 4},
        }
    )
    assert matrix == {"src": {"ruff:E501": 3}, "tests": {"ruff:F401": 4}}


# ---------------------------------------------------------------------------
# AnalysisReport structure
# ---------------------------------------------------------------------------


def test_areas_are_ordered_by_weight_so_the_shape_is_visible() -> None:
    measurement = _ruff_measurement({"small/a.py": {"ruff:E501": 1}, "big/b.py": {"ruff:E501": 30}}, files=2)
    baseline = {"small/a.py": {"ruff:E501": 1}, "big/b.py": {"ruff:E501": 30}}
    report = report_from_measurement(baseline, ("ruff",), measurement)
    assert report.sections[0].areas == ("big", "small")


def test_new_violations_get_their_own_section() -> None:
    measurement = _ruff_measurement({"src/a.py": {"ruff:E501": 3}}, files=1)
    report = report_from_measurement({}, ("ruff",), measurement)
    rendered = render_analysis_report(report)
    assert "## New violations" in rendered
    assert "`ruff:E501` | 3" in rendered


# ---------------------------------------------------------------------------
# "Nobody looked" vs "no debt" — the core invariant
# ---------------------------------------------------------------------------


def test_nobody_looked_reads_differently_from_no_debt() -> None:
    """A failed analyzer must render differently from one that found nothing."""
    looked = render_analysis_report(report_from_measurement({}, ("ruff",), _ruff_measurement({})))
    did_not = render_analysis_report(
        report_from_measurement(
            {},
            ("ruff",),
            Measurement(
                analyzers={
                    "ruff": Failed(
                        tool="ruff", failure_kind="execution-failed", detail="ruff is not installed here"
                    )
                }
            ),
        )
    )
    assert "ruff did not run" in did_not
    assert "ruff is not installed here" in did_not
    assert "ruff did not run" not in looked


def test_an_unavailable_analyzer_is_not_reported_as_zero_findings() -> None:
    """An unavailable analyzer must show 'not measured', not a zero count."""
    measurement = Measurement(analyzers={"mypy": Unavailable(tool="mypy", detail="mypy is not installed")})
    report = report_from_measurement({}, ("mypy",), measurement)
    rendered = render_analysis_report(report)
    assert "not measured" in rendered
    _, summary = report.analyzers[0]
    assert summary.findings is None


# ---------------------------------------------------------------------------
# Brief's named tests
# ---------------------------------------------------------------------------


def test_report_status_is_one_of_the_four_analyzer_states() -> None:
    """Every AnalyzerSummary.status is one of the four AnalyzerStatus literals."""
    valid_statuses = {"complete", "incomplete", "unavailable", "failed"}
    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            "mypy": Failed(tool="mypy", failure_kind="execution-failed", detail="mypy died"),
        }
    )
    report = report_from_measurement({}, ("ruff", "mypy"), measurement)
    for _, summary in report.analyzers:
        assert summary.status in valid_statuses


def test_an_incomplete_analyzer_reports_its_unattributed_count_and_samples() -> None:
    """An analyzer with syntax errors reports unattributed_total and up to 5 samples."""
    findings = tuple(UnattributedFinding(file=f"f{i}.py", line=i, message="SyntaxError") for i in range(7))
    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells={}, unattributed=findings, files_with_findings=0),
            )
        }
    )
    report = report_from_measurement({}, ("ruff",), measurement)
    _, summary = report.analyzers[0]
    assert summary.status == "incomplete"
    assert summary.unattributed_total == 7
    assert len(summary.unattributed) == 5  # capped at _WORST_SAMPLE


def test_an_unavailable_analyzer_reports_null_findings_and_a_failure_detail() -> None:
    """An unavailable analyzer has findings=None and failure=the detail string."""
    measurement = Measurement(analyzers={"mypy": Unavailable(tool="mypy", detail="mypy is not installed")})
    report = report_from_measurement({}, ("mypy",), measurement)
    _, summary = report.analyzers[0]
    assert summary.status == "unavailable"
    assert summary.findings is None
    assert summary.failure == "mypy is not installed"


def test_a_failed_analyzer_falls_back_to_its_baseline_and_says_so() -> None:
    """A failed contract analyzer uses its baseline cells as the backlog fallback."""
    baseline = {"src/a.py": {"ruff:E501": 3}}
    measurement = Measurement(
        analyzers={"ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff crashed")}
    )
    report = report_from_measurement(baseline, ("ruff",), measurement)
    # backlog comes entirely from baseline since ruff failed
    assert report.backlog_total == 3
    rendered = render_analysis_report(report)
    assert "ruff did not run" in rendered
    assert "ruff crashed" in rendered


def test_an_incomplete_contract_analyzer_shows_its_syntax_errors_in_the_markdown() -> None:
    """An analyzer left incomplete by a syntax error has failure=None, so the failure
    banner alone would render only 'incomplete' in the table. The Markdown must still name
    the unparsed files and warn that the backlog fell back to the baseline, matching what
    the JSON carries."""
    findings = (UnattributedFinding(file="src/broken.py", line=3, message="SyntaxError: bad token"),)
    baseline = {"src/a.py": {"ruff:E501": 2}}
    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells={}, unattributed=findings, files_with_findings=0),
            )
        }
    )

    rendered = render_analysis_report(report_from_measurement(baseline, ("ruff",), measurement))

    assert "src/broken.py:3" in rendered
    assert "SyntaxError: bad token" in rendered
    assert "baseline" in rendered.lower()
    assert ".ebpy/baseline.json" in rendered


def test_a_failed_out_of_contract_analyzer_still_shows_its_failure_reason() -> None:
    """A fresh repository has no contract, so every analyzer is out of contract. A failed run's
    reason must still reach the Markdown — "nobody looked" cannot render as "nothing found" just
    because there is no ceiling yet. The consequence line notes the analyzer has no ceiling rather
    than claiming a baseline fallback."""
    measurement = Measurement(
        analyzers={
            "mypy": Failed(
                tool="mypy", failure_kind="execution-failed", detail="mypy.ini: invalid option 'foo'"
            )
        }
    )

    rendered = render_analysis_report(report_from_measurement({}, (), measurement))

    assert "mypy did not run" in rendered
    assert "mypy.ini: invalid option 'foo'" in rendered
    # Out of contract: the consequence must not claim a baseline fallback that does not exist.
    assert ".ebpy/baseline.json" not in rendered


def test_an_incomplete_out_of_contract_analyzer_names_its_unparsed_files() -> None:
    """An out-of-contract analyzer left incomplete by a syntax error must still name the files it
    could not parse — the same detail an in-contract incomplete run gets, minus the baseline
    consequence."""
    findings = (UnattributedFinding(file="src/broken.py", line=9, message="SyntaxError: bad token"),)
    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells={}, unattributed=findings, files_with_findings=0),
            )
        }
    )

    rendered = render_analysis_report(report_from_measurement({}, (), measurement))

    assert "src/broken.py:9" in rendered
    assert "SyntaxError: bad token" in rendered


def test_a_contract_analyzer_with_no_runner_is_named_in_a_banner() -> None:
    """A contract naming an analyzer this build cannot run classifies as failed but carries no tool
    detail (observation is None). It must still produce a banner rather than silently rendering only
    'failed' in the table — a missing runner is exactly the kind of unmeasured state the banners
    exist to surface."""
    report = report_from_measurement({}, ("mypy",), Measurement(analyzers={}))

    rendered = render_analysis_report(report)

    assert "mypy did not run" in rendered
    assert "no runner" in rendered


def test_a_non_contract_analyzer_appears_only_under_unratcheted_analyzers() -> None:
    """A complete non-contract analyzer is excluded from new/backlog but shown as unratcheted."""
    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells={"src/a.py": {"ruff:E501": 2}}, files_with_findings=1),
            ),
        }
    )
    # ruff is NOT in frozen_analyzers (empty contract)
    report = report_from_measurement({}, (), measurement)
    assert report.new_total == 0
    assert report.backlog_total == 0
    rendered = render_analysis_report(report)
    assert "## Unratcheted analyzers" in rendered
    assert "`ruff`" in rendered


def test_the_backlog_matrix_merges_every_complete_contract_analyzer() -> None:
    """The backlog is the pruned union of all complete contract analyzers."""
    baseline = {
        "src/a.py": {"ruff:E501": 4, "mypy:arg-type": 2},
    }
    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells={"src/a.py": {"ruff:E501": 3}}, files_with_findings=1),
            ),
            "mypy": Measured(
                tool="mypy",
                value=AnalysisMeasurement(cells={"src/a.py": {"mypy:arg-type": 1}}, files_with_findings=1),
            ),
        }
    )
    report = report_from_measurement(baseline, ("ruff", "mypy"), measurement)
    # min(4,3)=3 for ruff + min(2,1)=1 for mypy = total 4
    assert report.backlog_total == 4


def test_the_json_has_no_mypy_errors_lint_failure_or_global_files_with_findings() -> None:
    """The JSON output must not contain the removed fields from the old schema."""
    measurement = _ruff_measurement({})
    report = report_from_measurement({}, ("ruff",), measurement)
    payload = report.to_dict()
    assert "mypyErrors" not in payload
    assert "lintFailure" not in payload
    assert "mypyFailure" not in payload
    # global filesWithFindings is removed; per-analyzer sits inside `analyzers`
    assert "filesWithFindings" not in payload
    assert "analyzers" in payload


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------


def test_the_report_serialises_for_json() -> None:
    baseline = {"src/a.py": {"ruff:F401": 2}}
    measurement = _ruff_measurement({"src/a.py": {"ruff:F401": 2}}, files=1)
    report = report_from_measurement(baseline, ("ruff",), measurement)
    payload = report.to_dict()
    assert payload["newTotal"] == 0
    assert payload["backlogTotal"] == 2
    assert payload["sections"][0]["rows"][0]["rule"] == "ruff:F401"
    analyzer = payload["analyzers"]["ruff"]
    assert analyzer["inContract"] is True
    assert analyzer["status"] == "complete"
    assert analyzer["findings"] == 2
    assert analyzer["filesWithFindings"] == 1
    assert analyzer["failure"] is None
    assert analyzer["unattributedTotal"] == 0
    assert analyzer["unattributed"] == []
