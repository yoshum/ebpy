"""Scan the history and the working tree for committed credentials."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..repo.git import is_git_repository
from ..secret_scan import (
    FOUND_IN_HISTORY,
    FOUND_IN_WORKING_TREE,
    MISSING_GITLEAKS,
    NOT_A_REPOSITORY,
    SECRET_FINDING_EXIT_CODE,
    SecretVerdict,
    combine_scans,
    interpret_gitleaks,
)
from ..util import run

if TYPE_CHECKING:
    from pathlib import Path

_FLAGS = ["--redact", "--verbose", "--exit-code", str(SECRET_FINDING_EXIT_CODE)]

# Two scans, because either one alone passes a repository that is holding a secret.
#
# `git` reads the history — a key committed and then deleted is still in every clone,
# and that is the one a working-tree scan cannot see. `dir` reads the files as they are
# now, which is the key pasted an hour ago and not committed yet: `git` reports "no leaks
# found" for it, and for a repository with no commits at all it reports that having read
# nothing. `dir` honours .gitignore, so a virtualenv costs nothing.
_SCANS: tuple[tuple[list[str], str], ...] = (
    (["git", ".", *_FLAGS], FOUND_IN_HISTORY),
    (["dir", ".", *_FLAGS], FOUND_IN_WORKING_TREE),
)


def run_secrets(cwd: Path) -> SecretVerdict:
    # Measured, not assumed: outside a work tree `gitleaks git` logs an error, scans
    # zero commits, and exits 0. Passing that on would be a clean result for a scan
    # that read nothing.
    if not is_git_repository(cwd):
        return SecretVerdict(ok=False, code=1, message=NOT_A_REPOSITORY)
    verdicts: list[SecretVerdict] = []
    for args, found in _SCANS:
        try:
            result = run(["gitleaks", *args], cwd)
        except OSError:
            # Spawning failed outright, which on every platform here means the binary
            # is not there.
            return SecretVerdict(ok=False, code=1, message=MISSING_GITLEAKS)
        verdicts.append(interpret_gitleaks(result.code, f"{result.stdout}\n{result.stderr}", found))
    return combine_scans(verdicts)
