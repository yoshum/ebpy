"""What CI actually runs, read as text rather than parsed YAML.

``runs-on`` may be a matrix expression, a string, or a list, and all we need is
"which runners does this repo actually exercise". Adding a YAML parser to
answer that would buy precision nobody uses.
"""

from __future__ import annotations

import re

from ..models import CiCoverage, WorkflowFile

# `latest` or a version (`22.04`, `13`, `2022`). Loosening the suffix to any word would
# match workflow FILENAMES like `windows-daily.yaml` and report a runner never used.
_RUNNER_PATTERN = re.compile(r"(?:ubuntu|macos|windows)-(?:latest|\d[\w.]*)")


def detect_ci(workflows: tuple[WorkflowFile, ...]) -> CiCoverage:
    combined = "\n".join(workflow.content for workflow in workflows)
    runners = tuple(sorted(set(_RUNNER_PATTERN.findall(combined))))
    return CiCoverage(
        present=len(workflows) > 0,
        runners=runners,
        runs_lint=bool(re.search(r"\bruff\s+check\b|\bflake8\b|\bpylint\b", combined)),
        runs_typecheck=bool(re.search(r"\bmypy\b|\bpyright\b", combined)),
        runs_test=bool(re.search(r"\bpytest\b|\bpython\s+-m\s+unittest\b", combined)),
        # The baseline is only a ratchet if something rejects a regression. A repo can
        # have thorough CI and still enforce nothing, which looks identical from outside.
        runs_ebpy_check=bool(re.search(r"ebpy\s+check", combined)),
    )


def missing_runners(coverage: CiCoverage) -> list[str]:
    families = {runner.split("-")[0] for runner in coverage.runners}
    return [family for family in ("ubuntu", "macos", "windows") if family not in families]
