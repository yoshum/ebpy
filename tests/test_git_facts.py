"""What git can and cannot answer about a clone whose history has been cut.

A shallow clone is the case that matters here: `git rev-list --count` reports a truncated
distance with exit 0, so a caller that trusts the number records one that is plausible,
systematically low, and wrong.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, NamedTuple

import pytest

from ebpy.models import State
from ebpy.quality_file import freshness_of
from ebpy.repo.git import commits_since, history_is_complete

if TYPE_CHECKING:
    from pathlib import Path

# Deep enough to reach the root along the short first-parent line and still cut the long
# side branch, which is what leaves the range's endpoint present while the walk is truncated.
CLONE_DEPTH = 4


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


class Origin(NamedTuple):
    """A repository and the root commit every distance here is measured from."""

    path: Path
    root: str


@pytest.fixture
def origin(tmp_path: Path) -> Origin:
    """Build a repository whose history is a short main line and a long merged side branch."""
    # The shape is what makes the trap reachable: a clone shallow enough to cut the side branch
    # still reaches the root along the main line, so `root..HEAD` has both endpoints in hand and
    # only the middle missing — the one case where git answers with a number instead of an error.
    path = tmp_path / "origin"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "user.name", "Test")

    (path / "f").write_text("root\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "root")
    root = git(path, "rev-parse", "HEAD")

    git(path, "checkout", "-q", "-b", "side")
    for index in range(5):
        (path / "s").write_text(f"side {index}\n", encoding="utf-8")
        git(path, "add", "-A")
        git(path, "commit", "-qm", f"side {index}")

    git(path, "checkout", "-q", "main")
    for index in range(2):
        (path / "f").write_text(f"main {index}\n", encoding="utf-8")
        git(path, "add", "-A")
        git(path, "commit", "-qm", f"main {index}")
    git(path, "merge", "-q", "--no-ff", "side", "-m", "merge")

    return Origin(path, root)


@pytest.fixture
def shallow(tmp_path: Path, origin: Origin) -> Origin:
    path = tmp_path / "shallow"
    # file:// because git ignores --depth for a plain local path and clones the whole history.
    git(tmp_path, "clone", "-q", f"--depth={CLONE_DEPTH}", origin.path.as_uri(), str(path))
    return Origin(path, origin.root)


def test_history_is_complete_in_a_whole_clone(origin: Origin) -> None:
    assert history_is_complete(origin.path) is True


def test_history_is_not_complete_in_a_shallow_clone(shallow: Origin) -> None:
    assert history_is_complete(shallow.path) is False


def test_history_completeness_is_unknown_outside_a_repository(tmp_path: Path) -> None:
    assert history_is_complete(tmp_path) is None


def test_commits_since_counts_the_distance_in_a_whole_clone(origin: Origin) -> None:
    assert commits_since(origin.path, origin.root) == 8


def test_commits_since_is_unknown_in_a_shallow_clone(shallow: Origin) -> None:
    assert commits_since(shallow.path, shallow.root) is None


def test_a_shallow_clone_is_the_case_git_answers_wrongly_rather_than_refusing(
    origin: Origin, shallow: Origin
) -> None:
    """Pin the trap the check exists for, so a future simplification cannot quietly undo it."""
    truncated = git(shallow.path, "rev-list", "--count", f"{shallow.root}..HEAD")
    whole = git(origin.path, "rev-list", "--count", f"{origin.root}..HEAD")

    # Neither the endpoint being on disk nor a zero exit reveals the cut, so neither could
    # stand in for asking git whether the clone is shallow.
    assert git(shallow.path, "cat-file", "-t", shallow.root) == "commit"
    assert int(truncated) < int(whole)


def test_a_shallow_clone_reports_the_distance_as_unknown_rather_than_current(shallow: Origin) -> None:
    """Report a moved HEAD as stale when the distance to it cannot be counted."""
    # The distance decides staleness, so an undercount is what would declare this one current.
    diagnosed_at = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
    state = State(diagnosed_at=diagnosed_at, diagnosed_commit=shallow.root)

    verdict = freshness_of(shallow.path, state)

    assert verdict.stale
    assert "distance is unknown" in verdict.reason


def test_a_whole_clone_still_calls_a_short_distance_current(origin: Origin) -> None:
    diagnosed_at = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
    state = State(diagnosed_at=diagnosed_at, diagnosed_commit=origin.root)

    assert not freshness_of(origin.path, state).stale
