"""The backlog as a rule x area table, for a terminal or a CI job summary."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..analysis.lint_report import LintReport, Unmeasured, build_lint_report, matrix_from_cells
from ..errors import CommandError
from ..measurement import Measured, Measurement, measure_repository
from ..models import MYPY_COUNTER, CellCounts
from ..persist.baseline import prune_cells, split_against_baseline
from ..persist.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..render.lint_report import render_lint_report

# Actions sets this to a file every job may append markdown to. Writing there is what
# makes this a CI report without anyone editing a workflow, and outside Actions it is
# unset so a terminal run only ever prints.
_STEP_SUMMARY = "GITHUB_STEP_SUMMARY"


def _append_to_step_summary(markdown: str) -> None:
    target = os.environ.get(_STEP_SUMMARY)
    if not target:
        return
    # A report is not a gate. Failing the job because the summary could not be written
    # would make it one, and the markdown has already gone to stdout either way.
    try:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    except OSError:
        return


def report_from_measurement(baseline: CellCounts, measurement: Measurement) -> LintReport:
    """Build a report from facts; tool failure changes its detail, never its exit status."""
    mypy = measurement.counters[MYPY_COUNTER]
    mypy_errors = mypy.value if isinstance(mypy, Measured) else None
    mypy_failure = mypy.detail if not isinstance(mypy, Measured) else None

    lint = measurement.lint
    if not isinstance(lint, Measured):
        return build_lint_report(
            new_by_rule=None,
            backlog_matrix=matrix_from_cells(baseline),
            mypy_errors=mypy_errors,
            files_with_findings=0,
            unmeasured=Unmeasured(lint=lint.detail, mypy=mypy_failure),
        )

    result = lint.value
    new_by_rule, _ = split_against_baseline(result.cells, baseline)
    # The backlog is what the ratchet still holds: the baseline lowered to what
    # still exists, not today's raw counts which include violations above it.
    held = prune_cells(baseline, result.cells)
    return build_lint_report(
        new_by_rule=new_by_rule,
        backlog_matrix=matrix_from_cells(held),
        mypy_errors=mypy_errors,
        files_with_findings=result.files_with_findings,
        unmeasured=Unmeasured(mypy=mypy_failure),
    )


def run_report(cwd: Path, as_json: bool) -> str:
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        raise CommandError(invalid_artifacts_message(artifacts))

    report = report_from_measurement(artifacts.cells, measure_repository(cwd))

    if as_json:
        return json.dumps(report.to_dict(), indent=2)
    markdown = render_lint_report(report)
    _append_to_step_summary(markdown)
    return markdown
