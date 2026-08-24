"""Process execution, in one place."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class ExecResult:
    """The result of running a subprocess: its exit code, stdout and stderr."""

    code: int
    stdout: str
    stderr: str


def run(argv: list[str], cwd: Path) -> ExecResult:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return ExecResult(code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
