"""Counts mypy errors, when mypy is there to count them.

Type errors have no suppression file and no ``--suppress-all``: they cannot be
grandfathered per file per rule the way lint violations are. Their total gets a
plain ratcheted counter instead, so the number can fall but never rise.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .cell_key import normalize_analyzer_path, qualify_rule
from .errors import ToolError
from .models import AnalysisMeasurement, CellCounts
from .util import run

# "path.py:12: error: ..." — counting these rather than trusting the summary line,
# because the summary is absent under --no-error-summary and localised under others.
_ERROR_LINE = re.compile(r"^.+?:\d+(?::\d+)?: error: ", re.MULTILINE)

# A parseable error line: `<file>:<line>[:<column>[:<end-line>:<end-column>]]: error: <message>  [<code>]`.
# The filename group is non-greedy. mypy's own filenames can contain a colon — a Windows
# drive letter, or a literal colon in the path — so a greedy group would swallow the first
# `: error: ` it could find instead of the real one. Backtracking from the left lets the
# engine walk the filename forward past a false location match until it reaches the digit
# groups that are actually followed by `: error: `.
_MYPY_ERROR_LINE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+)"
    r"(?::(?P<column>\d+))?"
    r"(?::(?P<end_line>\d+):(?P<end_column>\d+))?"
    r": error: (?P<message>.*?)\s+\[(?P<code>[^\[\]\s]+)\]$"
)

# Long enough for a config error or a missing-stubs line, short enough to stay one line.
_SUMMARY_LIMIT = 200


class MypyNotFoundError(ToolError):
    pass


class MypyFailedError(ToolError):
    pass


class MypyInvalidOutputError(MypyFailedError):
    pass


def find_mypy(cwd: Path) -> list[str] | None:
    for venv in (".venv", "venv"):
        for bindir, exe in (("bin", "mypy"), ("Scripts", "mypy.exe")):
            candidate = cwd / venv / bindir / exe
            if candidate.is_file():
                return [str(candidate)]
    on_path = shutil.which("mypy")
    return [on_path] if on_path else None


def count_errors(output: str) -> int:
    return len(_ERROR_LINE.findall(output))


def parse_mypy_output(output: str, cwd: Path) -> AnalysisMeasurement:
    """Turn mypy's text output into cells keyed like Ruff's, under the `mypy:` namespace."""
    cells: CellCounts = {}
    seen_files: set[str] = set()
    for line in output.splitlines():
        if ": error: " not in line:
            continue
        match = _MYPY_ERROR_LINE.match(line)
        if match is None:
            # A code mypy did report but this parser failed to read would silently
            # disappear from the count, which is worse than refusing to measure at all.
            raise MypyInvalidOutputError(f"mypy produced an unparseable error line: {line!r}")
        file = normalize_analyzer_path(match["file"], cwd)
        rule = qualify_rule("mypy", match["code"])
        seen_files.add(file)
        cells.setdefault(file, {})[rule] = cells.get(file, {}).get(rule, 0) + 1
    return AnalysisMeasurement(cells=cells, files_with_findings=len(seen_files))


def _summary_clause(output: str) -> str:
    """The one line of mypy's complaint a human acts on, for the summary reading.

    Which line that is depends on how mypy failed: a rejected argument prints a two-line
    usage banner and puts ``mypy: error: ...`` last, while a bad config file prints its
    complaint alone. Preferring the last error line and falling back to the first covers
    both without parsing either. The whole output still travels as the detail.
    """
    lines = [text for line in output.splitlines() if (text := line.strip())]
    if not lines:
        return ""
    errors = [line for line in lines if "error:" in line]
    return f": {(errors[-1] if errors else lines[0])[:_SUMMARY_LIMIT]}"


def run_mypy_check(cwd: Path) -> int:
    """Today's mypy error total, raising when no number was measured."""
    argv = find_mypy(cwd)
    if not argv:
        raise MypyNotFoundError(
            "mypy is not installed here (looked in .venv, venv and PATH). Run `ebpy bootstrap` first."
        )
    try:
        result = run([*argv, ".", "--no-error-summary"], cwd)
    except OSError as error:
        raise MypyFailedError(f"mypy could not run: {error}") from error
    # 0 = clean, 1 = errors found; only those two mean mypy actually ran. Positive
    # alternatives are mypy failures, while a negative return code means a signal
    # terminated the process — neither produced a trustworthy number.
    if result.code not in (0, 1):
        headline = f"mypy failed (exit {result.code})"
        output = (result.stderr or result.stdout).strip()
        raise MypyFailedError(
            f"{headline}{_summary_clause(output)}",
            detail=f"{headline}:\n{output}" if output else headline,
        )
    return count_errors(result.stdout)
