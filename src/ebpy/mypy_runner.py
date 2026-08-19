"""Counts mypy errors, when mypy is there to count them.

Type errors have no suppression file and no ``--suppress-all``: they cannot be
grandfathered per file per rule the way lint violations are. Their total gets a
plain ratcheted counter instead, so the number can fall but never rise.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .errors import ToolError
from .util import run

# "path.py:12: error: ..." — counting these rather than trusting the summary line,
# because the summary is absent under --no-error-summary and localised under others.
_ERROR_LINE = re.compile(r"^.+?:\d+(?::\d+)?: error: ", re.MULTILINE)

# Long enough for a config error or a missing-stubs line, short enough to stay one line.
_SUMMARY_LIMIT = 200


class MypyNotFoundError(ToolError):
    pass


class MypyFailedError(ToolError):
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
