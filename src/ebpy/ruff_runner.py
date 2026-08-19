"""Runs the target repo's own Ruff — not a bundled one.

A repo's rule selection and Ruff version are part of what is being measured, so
borrowing a different Ruff would produce a baseline no developer in that repo
can reproduce. The project virtualenv is preferred; PATH is the fallback.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

from .models import CellCounts, LintMeasurement, UnattributedFinding
from .util import run


class RuffNotFoundError(RuntimeError):
    pass


class RuffFailedError(RuntimeError):
    pass


class RuffInvalidOutputError(RuffFailedError):
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


def parse_ruff_json(stdout: str, cwd: Path) -> LintMeasurement:
    raw: Any = json.loads(stdout or "[]")
    if not isinstance(raw, list):
        raise RuffInvalidOutputError("ruff produced JSON of an unexpected shape")
    cells: CellCounts = {}
    unattributed: list[UnattributedFinding] = []
    seen_files: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise RuffInvalidOutputError(f"ruff produced an invalid diagnostic at index {index}")
        filename = item.get("filename")
        code = item.get("code")
        message = item.get("message")
        location = item.get("location")
        if (
            not isinstance(filename, str)
            or not filename
            or (code is not None and (not isinstance(code, str) or not code))
            or not isinstance(message, str)
            or not isinstance(location, dict)
            or type(location.get("row")) is not int
        ):
            raise RuffInvalidOutputError(f"ruff produced an invalid diagnostic at index {index}")
        file = _relative_posix(filename, cwd)
        seen_files.add(file)
        if not code or code == "invalid-syntax":
            unattributed.append(
                UnattributedFinding(
                    file=file,
                    line=location["row"],
                    message=message,
                )
            )
            continue
        cells.setdefault(file, {})[str(code)] = cells.get(file, {}).get(str(code), 0) + 1
    return LintMeasurement(
        cells=cells,
        unattributed=tuple(unattributed),
        files_with_findings=len(seen_files),
    )


def run_ruff_check(cwd: Path) -> LintMeasurement:
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
        raise RuffInvalidOutputError(f"ruff produced unparseable output: {error}") from error
