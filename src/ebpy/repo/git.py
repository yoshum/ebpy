"""Git questions the ledger needs answered."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ebpy.util import run

if TYPE_CHECKING:
    from pathlib import Path

_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def is_git_repository(cwd: Path) -> bool:
    """Report whether there is a git history here at all.

    A caller that scans one has to ask first: ``gitleaks git`` outside a work tree logs an
    error, scans zero commits, and still exits 0 with "no leaks found" — a clean bill of
    health for a scan that looked at nothing.
    """
    try:
        result = run(["git", "rev-parse", "--is-inside-work-tree"], cwd)
    except OSError:
        return False
    return result.code == 0 and result.stdout.strip() == "true"


def head_commit(cwd: Path) -> str | None:
    """Return the current HEAD sha, or None when it cannot be resolved or is malformed."""
    try:
        result = run(["git", "rev-parse", "HEAD"], cwd)
    except OSError:
        return None
    if result.code != 0:
        return None
    sha = result.stdout.strip()
    return sha if _SHA.match(sha) else None


def history_is_complete(cwd: Path) -> bool | None:
    """Report whether this clone holds the whole history.

    False is a shallow clone, where no commit distance can be trusted. None is git declining to
    answer, which a caller must not read as a complete history.
    """
    # Asked of git rather than read off the objects, because shallowness is a declared cut and
    # not an absence: `.git/shallow` names commits git walks as though they had no parents, so a
    # boundary's parent can sit on disk and still be unreachable. No object shows the cut.
    try:
        result = run(["git", "rev-parse", "--is-shallow-repository"], cwd)
    except OSError:
        return None
    # A git older than 2.15 has no --is-shallow-repository and fails the call instead of
    # answering it. That is unknown, not complete.
    if result.code != 0:
        return None
    answer = result.stdout.strip()
    return answer == "false" if answer in {"true", "false"} else None


def commits_since(cwd: Path, sha: str | None) -> int | None:
    """Count how far the repository has moved since a diagnosis.

    None when the distance cannot be established: a rebase or force-push has left the recorded
    commit out of this history, or the clone is shallow. Either is a reason to re-diagnose
    rather than a number to guess at.
    """
    if not sha:
        return None
    # A shallow clone stops the walk at every graft boundary, so `rev-list --count` reports a
    # truncated distance with exit 0 — plausible, systematically low, silently wrong. Anything
    # short of a definite "complete" therefore leaves the distance unknown: a count nobody could
    # verify the history for must not be recorded as one that was measured.
    if history_is_complete(cwd) is not True:
        return None
    try:
        result = run(["git", "rev-list", "--count", f"{sha}..HEAD"], cwd)
    except OSError:
        return None
    if result.code != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def tracked_files(cwd: Path) -> list[str] | None:
    """Every tracked, non-ignored file, or None outside a repository."""
    try:
        result = run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd)
    except OSError:
        return None
    if result.code != 0:
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]
