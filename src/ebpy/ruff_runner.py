"""Runs the target repo's own Ruff — not a bundled one.

A repo's rule selection and Ruff version are part of what is being measured, so
borrowing a different Ruff would produce a baseline no developer in that repo
can reproduce. The project virtualenv is preferred; PATH is the fallback.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .baseline import CellCounts
from .util import run


@dataclass(frozen=True)
class Unattributed:
    file: str
    line: int
    message: str


@dataclass(frozen=True)
class RuffResult:
    """Today's violations, per file per rule — the shape the ratchet compares."""

    cells: CellCounts
    # Diagnostics Ruff could not attribute to a rule — syntax errors. The baseline
    # cannot grandfather these: a file that does not parse is invisible to every rule,
    # so its "count" would be a lie.
    unattributed: list[Unattributed] = field(default_factory=list)
    # Files Ruff reported something about — NOT the number it linted, which its JSON
    # output does not carry. A clean repository reports zero here.
    files_with_findings: int = 0


class RuffNotFoundError(RuntimeError):
    pass


class RuffFailedError(RuntimeError):
    pass


def find_ruff(cwd: Path) -> list[str] | None:
    for venv in (".venv", "venv"):
        for bindir, exe in (("bin", "ruff"), ("Scripts", "ruff.exe")):
            candidate = cwd / venv / bindir / exe
            if candidate.is_file():
                return [str(candidate)]
    on_path = shutil.which("ruff")
    return [on_path] if on_path else None


def _relative_posix(filename: str, cwd: Path) -> str:
    try:
        rel = Path(filename).resolve().relative_to(cwd.resolve())
    except ValueError:
        rel = Path(filename)
    return str(PurePosixPath(*rel.parts))


def parse_ruff_json(stdout: str, cwd: Path) -> RuffResult:
    raw: Any = json.loads(stdout or "[]")
    if not isinstance(raw, list):
        raise RuffFailedError("ruff produced JSON of an unexpected shape")
    cells: CellCounts = {}
    unattributed: list[Unattributed] = []
    seen_files: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        file = _relative_posix(str(item.get("filename", "")), cwd)
        seen_files.add(file)
        code = item.get("code")
        if not code or code == "invalid-syntax":
            location = item.get("location") or {}
            unattributed.append(
                Unattributed(
                    file=file, line=int(location.get("row") or 0), message=str(item.get("message", ""))
                )
            )
            continue
        cells.setdefault(file, {})[str(code)] = cells.get(file, {}).get(str(code), 0) + 1
    return RuffResult(cells=cells, unattributed=unattributed, files_with_findings=len(seen_files))


def run_ruff_check(cwd: Path) -> RuffResult:
    argv = find_ruff(cwd)
    if not argv:
        raise RuffNotFoundError(
            "ruff is not installed here (looked in .venv, venv and PATH). Run `ebpy bootstrap` first."
        )
    # --exit-zero: violations are the normal case for this tool, not a failure. A non-zero
    # exit then genuinely means Ruff itself could not run.
    result = run([*argv, "check", ".", "--output-format", "json", "--exit-zero"], cwd)
    if result.code != 0:
        raise RuffFailedError(f"ruff check failed (exit {result.code}):\n{result.stderr[:4000]}")
    try:
        return parse_ruff_json(result.stdout, cwd)
    except json.JSONDecodeError as error:
        raise RuffFailedError(f"ruff produced unparseable output: {error}") from error
