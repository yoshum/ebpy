"""Counts mypy errors, when mypy is there to count them.

Type errors have no suppression file and no ``--suppress-all``: they cannot be
grandfathered per file per rule the way lint violations are. Their total gets a
plain ratcheted counter instead, so the number can fall but never rise.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .util import run

# "path.py:12: error: ..." — counting these rather than trusting the summary line,
# because the summary is absent under --no-error-summary and localised under others.
_ERROR_LINE = re.compile(r"^.+?:\d+(?::\d+)?: error: ", re.MULTILINE)

_FATAL_EXIT = 2


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


def run_mypy_error_count(cwd: Path) -> int | None:
    """Today's mypy error total, or None when it could not be measured.

    None and 0 must stay distinct: a counter written from a run that never happened
    would ratchet the number to a value nobody measured.
    """
    argv = find_mypy(cwd)
    if not argv:
        return None
    try:
        result = run([*argv, ".", "--no-error-summary"], cwd)
    except OSError:
        return None
    # 0 = clean, 1 = errors found; both mean mypy actually ran. 2 is mypy itself failing
    # (bad config, missing stubs package aborting the run) — not a number.
    if result.code >= _FATAL_EXIT:
        return None
    return count_errors(result.stdout)
