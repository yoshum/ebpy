"""Terminal rendering of the diagnosis."""

from __future__ import annotations

from ..detect.sizes import DEFAULT_FILE_LINE_LIMIT
from ..models import Diagnosis, Gap


def _check(value: bool) -> str:
    return "yes" if value else "no"


def _tooling_lines(diagnosis: Diagnosis) -> list[str]:
    tooling = diagnosis.tooling
    mypy = "strict" if tooling.mypy_strict else ("yes (not strict)" if tooling.mypy else "no")
    return [
        f"  package manager   {diagnosis.package_manager}",
        f"  python            {diagnosis.requires_python or 'unspecified'}",
        f"  framework         {diagnosis.framework}",
        f"  ruff              {_check(tooling.ruff)}",
        f"  formatter         {_check(tooling.formatter)}",
        f"  mypy              {mypy}",
        f"  pytest            {_check(tooling.pytest)}",
        f"  vulture           {_check(tooling.vulture)}",
        f"  pre-commit        {_check(tooling.pre_commit)}",
        f"  secret scanning   {_check(tooling.secret_scanning)}",
        f"  agent rules       {', '.join(tooling.agent_instructions) or 'none'}",
    ]


def _ci_line(diagnosis: Diagnosis) -> str:
    if not diagnosis.ci.present:
        return "  ci                none"
    runners = ", ".join(diagnosis.ci.runners) or "unknown runners"
    steps = [
        name
        for name, present in (
            ("lint", diagnosis.ci.runs_lint),
            ("typecheck", diagnosis.ci.runs_typecheck),
            ("test", diagnosis.ci.runs_test),
            ("ebpy-check", diagnosis.ci.runs_ebpy_check),
        )
        if present
    ]
    return f"  ci                {runners} [{' '.join(steps) or 'no known steps'}]"


def _size_lines(diagnosis: Diagnosis) -> list[str]:
    return [
        f"  source files      {diagnosis.sizes.total}",
        f"  over {DEFAULT_FILE_LINE_LIMIT} lines     {diagnosis.sizes.over_file_limit}",
        *(f"                      {file.lines}  {file.path}" for file in diagnosis.sizes.largest[:3]),
    ]


def _gap_lines(gaps: tuple[Gap, ...]) -> list[str]:
    if not gaps:
        return ["", "No gaps found. Freeze the baseline and start draining."]
    lines = ["", f"{len(gaps)} gap(s):"]
    for gap in gaps:
        lines.append(f"  [{gap.phase}] {gap.title}")
        lines.append(f"      {gap.detail}")
    return lines


def render_diagnosis(diagnosis: Diagnosis) -> str:
    return "\n".join(
        [
            "ebpy diagnose",
            "",
            *_tooling_lines(diagnosis),
            _ci_line(diagnosis),
            *_size_lines(diagnosis),
            *_gap_lines(diagnosis.gaps),
            "",
        ]
    )
