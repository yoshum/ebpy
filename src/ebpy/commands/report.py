"""The backlog as a rule x area table, for a terminal or a CI job summary."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from ..baseline import prune_cells, read_cells, read_suppressions, split_against_baseline
from ..ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..lint_report import build_lint_report, matrix_from_cells, matrix_from_suppressions
from ..mypy_runner import run_mypy_error_count
from ..render.lint_report import render_lint_report
from ..ruff_runner import RuffResult, run_ruff_check

# Actions sets this to a file every job may append markdown to. Writing there is what
# makes this a CI report without anyone editing a workflow, and outside Actions it is
# unset so a terminal run only ever prints.
_STEP_SUMMARY = "GITHUB_STEP_SUMMARY"


@dataclass(frozen=True)
class ReportResult:
    ok: bool
    message: str


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


def _lint(cwd: Path) -> tuple[RuffResult | None, str | None]:
    """A report is not a gate, so a repository that cannot lint still gets the half of
    the answer the ratchet file holds. The reason travels with it — "no debt" and
    "nobody looked" have to read differently."""
    try:
        return run_ruff_check(cwd), None
    except (RuntimeError, OSError) as error:
        return None, str(error).split("\n")[0]


def run_report(cwd: Path, as_json: bool) -> ReportResult:
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        return ReportResult(ok=False, message=invalid_artifacts_message(artifacts))

    result, failure = _lint(cwd)
    baseline = read_cells(cwd)

    if result is None:
        report = build_lint_report(
            new_by_rule=None,
            backlog_matrix=matrix_from_suppressions(read_suppressions(cwd)),
            mypy_errors=None,
            files_with_findings=0,
            lint_failure=failure or "Ruff did not run",
        )
    else:
        new_by_rule, _ = split_against_baseline(result.cells, baseline)
        # The backlog is what the ratchet still holds: the baseline file lowered to what
        # still exists — not today's raw counts, which include the new violations above.
        held = prune_cells(baseline, result.cells)
        report = build_lint_report(
            new_by_rule=new_by_rule,
            backlog_matrix=matrix_from_cells(held),
            mypy_errors=run_mypy_error_count(cwd),
            files_with_findings=result.files_with_findings,
            lint_failure=None,
        )

    if as_json:
        return ReportResult(ok=True, message=json.dumps(report.to_dict(), indent=2))
    markdown = render_lint_report(report)
    _append_to_step_summary(markdown)
    return ReportResult(ok=True, message=markdown)
