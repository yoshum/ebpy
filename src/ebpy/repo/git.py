"""Git questions the ledger needs answered."""

from __future__ import annotations

import re
from pathlib import Path

from ..util import run

_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def is_git_repository(cwd: Path) -> bool:
    """Whether there is a history here at all. A caller that scans one has to ask first:
    ``gitleaks git`` outside a work tree logs an error, scans zero commits, and still
    exits 0 with "no leaks found" — a clean bill of health for a scan that looked at
    nothing."""
    try:
        result = run(["git", "rev-parse", "--is-inside-work-tree"], cwd)
    except OSError:
        return False
    return result.code == 0 and result.stdout.strip() == "true"


def head_commit(cwd: Path) -> str | None:
    try:
        result = run(["git", "rev-parse", "HEAD"], cwd)
    except OSError:
        return None
    if result.code != 0:
        return None
    sha = result.stdout.strip()
    return sha if _SHA.match(sha) else None


def commits_since(cwd: Path, sha: str | None) -> int | None:
    """How far the repository has moved since a diagnosis. None when the recorded commit
    is not in this history at all — after a rebase, a force-push, or a fresh shallow
    clone — which is itself a reason to re-diagnose rather than a number to guess at."""
    if not sha:
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
