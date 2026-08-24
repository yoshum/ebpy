"""Runs the target repo's own Ruff — not a bundled one.

A repo's rule selection and Ruff version are part of what is being measured, so
borrowing a different Ruff would produce a baseline no developer in that repo
can reproduce. The project virtualenv is preferred; PATH is the fallback.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ebpy.cell_key import normalize_analyzer_path, qualify_rule
from ebpy.errors import ToolError
from ebpy.models import AnalysisMeasurement, CellCounts, UnattributedFinding
from ebpy.util import run

if TYPE_CHECKING:
    from pathlib import Path

# Long enough for a config error, short enough to stay one line.
_SUMMARY_LIMIT = 200


class RuffNotFoundError(ToolError):
    pass


class RuffFailedError(ToolError):
    pass


class RuffInvalidOutputError(RuffFailedError):
    pass


def _summarize_cause(output: str) -> str:
    """Return the one line of Ruff's complaint a human acts on, for the summary reading.

    Ruff prints a bare `ruff failed`, then indented `Cause:` lines from the outermost
    cause inward. The first cause names what to go and fix; the ones below it explain
    that cause in more depth and belong in the detail, which carries all of it.
    """
    lines = [text for line in output.splitlines() if (text := line.strip())]
    if not lines:
        return ""
    causes = [line for line in lines if line.startswith("Cause:")]
    return f": {(causes[0] if causes else lines[0])[:_SUMMARY_LIMIT]}"


def find_ruff(cwd: Path) -> list[str] | None:
    for venv in (".venv", "venv"):
        for bindir, exe in (("bin", "ruff"), ("Scripts", "ruff.exe")):
            candidate = cwd / venv / bindir / exe
            if candidate.is_file():
                return [str(candidate)]
    on_path = shutil.which("ruff")
    return [on_path] if on_path else None


@dataclass(frozen=True)
class _Diagnostic:
    """One ruff finding, reduced to the fields a cell is keyed on.

    A `code` of None is ruff's way of reporting a finding with no rule (a syntax
    error); it is kept so parsing can route it to the unattributed list rather
    than a cell.
    """

    filename: str
    code: str | None
    message: str
    row: int


def _read_diagnostic(item: object) -> _Diagnostic | None:
    """Read one ruff JSON diagnostic, or None when it lacks a field a cell needs.

    Ruff's JSON is trusted only as far as its documented schema; a diagnostic
    missing its filename, message or integer row cannot be attributed to a cell,
    and an empty code is as unusable as a mistyped one. None is the one accepted
    absence, because ruff uses it for a syntax error that belongs nowhere.
    """
    if not isinstance(item, dict):
        return None
    filename = item.get("filename")
    code = item.get("code")
    message = item.get("message")
    location = item.get("location")
    if not isinstance(filename, str) or not filename:
        return None
    if code is not None and (not isinstance(code, str) or not code):
        return None
    if not isinstance(message, str) or not isinstance(location, dict):
        return None
    row = location.get("row")
    if type(row) is not int:
        return None
    return _Diagnostic(filename=filename, code=code, message=message, row=row)


def parse_ruff_json(stdout: str, cwd: Path) -> AnalysisMeasurement:
    raw: Any = json.loads(stdout or "[]")
    if not isinstance(raw, list):
        raise RuffInvalidOutputError("ruff produced JSON of an unexpected shape")
    cells: CellCounts = {}
    unattributed: list[UnattributedFinding] = []
    for index, item in enumerate(raw):
        diagnostic = _read_diagnostic(item)
        if diagnostic is None:
            raise RuffInvalidOutputError(f"ruff produced an invalid diagnostic at index {index}")
        file = normalize_analyzer_path(diagnostic.filename, cwd)
        if not diagnostic.code or diagnostic.code == "invalid-syntax":
            unattributed.append(
                UnattributedFinding(
                    file=file,
                    line=diagnostic.row,
                    message=diagnostic.message,
                )
            )
            continue
        rule = qualify_rule("ruff", diagnostic.code)
        file_cells = cells.setdefault(file, {})
        file_cells[rule] = file_cells.get(rule, 0) + 1
    return AnalysisMeasurement(
        cells=cells,
        unattributed=tuple(unattributed),
    )


def run_ruff_check(cwd: Path) -> AnalysisMeasurement:
    argv = find_ruff(cwd)
    if not argv:
        raise RuffNotFoundError(
            "ruff is not installed here (looked in .venv, venv and PATH). Run `ebpy bootstrap` first."
        )
    # --exit-zero: violations are the normal case for this tool, not a failure. A non-zero
    # exit then genuinely means Ruff itself could not run.
    result = run([*argv, "check", ".", "--output-format", "json", "--exit-zero"], cwd)
    if result.code != 0:
        headline = f"ruff check failed (exit {result.code})"
        output = result.stderr.strip()
        raise RuffFailedError(
            f"{headline}{_summarize_cause(output)}",
            detail=f"{headline}:\n{output}" if output else headline,
        )
    try:
        return parse_ruff_json(result.stdout, cwd)
    except json.JSONDecodeError as error:
        raise RuffInvalidOutputError(f"ruff produced unparseable output: {error}") from error
