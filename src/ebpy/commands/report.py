"""The backlog as a rule x area table, for a terminal or a CI job summary."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from ebpy.decide.analysis_report import report_from_measurement
from ebpy.decide.analyzer_scope import empty_scope_message, scope_decision
from ebpy.errors import CommandError
from ebpy.render.analysis_report import render_analysis_report
from ebpy.repo.detect.language import detect_languages
from ebpy.store.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ebpy.store.config import read_config
from ebpy.store.state import empty_state
from ebpy.tools import measure_repository

if TYPE_CHECKING:
    from pathlib import Path

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


def run_report(cwd: Path, as_json: bool) -> str:
    """Run ``ebpy report``: render every rule's standing against the frozen contract."""
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        raise CommandError(invalid_artifacts_message(artifacts))

    # A fresh (unfrozen) repository has no contract yet; every analyzer is unratcheted.
    if artifacts.kind == "fresh":
        frozen_analyzers: tuple[str, ...] = ()
        previous = empty_state()
    else:
        state = artifacts.ledger.state
        assert state is not None
        frozen_analyzers = state.frozen_analyzers
        previous = state

    scope = scope_decision(read_config(cwd), detect_languages(cwd), previous)
    # A mismatch is what a reader ran `report` to see, so it is rendered rather than raised
    # (D-14). An empty scope only refuses when there is also no contract: with nothing
    # measured and nothing frozen there is no standing left to show.
    if not scope.to_measure and not frozen_analyzers:
        raise CommandError(empty_scope_message(scope))

    report = report_from_measurement(
        artifacts.cells, frozen_analyzers, measure_repository(cwd, scope.to_measure)
    )

    if as_json:
        return json.dumps(report.to_dict(), indent=2)
    markdown = render_analysis_report(report)
    _append_to_step_summary(markdown)
    return markdown
