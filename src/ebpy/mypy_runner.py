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


class MypyNotFoundError(RuntimeError):
    pass


class MypyFailedError(RuntimeError):
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
    # 0 = clean, 1 = errors found; both mean mypy actually ran. 2 is mypy itself failing
    # (bad config, missing stubs package aborting the run) — not a number.
    if result.code >= _FATAL_EXIT:
        detail = (result.stderr or result.stdout).strip()
        suffix = f":\n{detail[:4000]}" if detail else ""
        raise MypyFailedError(f"mypy failed (exit {result.code}){suffix}")
    return count_errors(result.stdout)
