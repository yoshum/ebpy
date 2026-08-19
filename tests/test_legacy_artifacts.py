"""Pin how ebpy treats artifacts written by an earlier, pre-version-2 ebpy.

Version 1 is no longer read or upgraded: a repository frozen with an earlier ebpy reads as
invalid, and the message sends the user to `ebpy freeze --force` to re-pin. These tests write
on-disk fixtures into `tmp_path` and exercise the real reader `read_ceiling_artifacts`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ebpy.baseline import baseline_path
from ebpy.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ebpy.state import state_path

_FROZEN_AT = "2026-08-19T00:00:00Z"
_RULE_LOCAL = "F401"
_FILE = "src/app.py"
_COUNT = 2


def _write_v1_state(cwd: Path, *, counters: dict[str, Any] | None = None) -> None:
    """Write a minimal version-1 state.json, the shape an earlier ebpy produced."""
    raw: dict[str, Any] = {
        "version": 1,
        "tool": "ebpy",
        "phase": "drain",
        "updatedAt": _FROZEN_AT,
        "frozenAt": _FROZEN_AT,
        "diagnosedAt": None,
        "diagnosedCommit": None,
        "diagnosis": None,
        "rules": {_RULE_LOCAL: {"baseline": _COUNT, "current": _COUNT, "status": "draining"}},
        "counters": counters if counters is not None else {"mypy:errors": {"baseline": 0, "current": 0}},
        "log": [],
    }
    path = state_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw) + "\n", encoding="utf-8")


def _write_v1_baseline(cwd: Path) -> None:
    """Write a version-1 baseline.json using bare (unnamespaced) rule keys."""
    raw = {_FILE: {_RULE_LOCAL: {"count": _COUNT}}}
    path = baseline_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw) + "\n", encoding="utf-8")


def test_a_version_one_state_reads_as_invalid_rather_than_upgrading(tmp_path: Path) -> None:
    """A state.json still at version 1 is no longer normalised in memory; it is refused so the
    reader never guesses at a contract from a format it no longer understands."""
    _write_v1_baseline(tmp_path)
    _write_v1_state(tmp_path)

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_a_bare_unversioned_baseline_reads_as_invalid(tmp_path: Path) -> None:
    """A baseline.json with bare rule keys and no version wrapper is a version-1 artifact; it is
    unreadable rather than silently reinterpreted as version 2."""
    _write_v1_baseline(tmp_path)

    ceiling = read_ceiling_artifacts(tmp_path)
    assert ceiling.kind == "invalid"


def test_the_refusal_points_at_freeze_force(tmp_path: Path) -> None:
    """The invalid-artifacts message must name `ebpy freeze --force`, the only way to re-pin a
    contract over an artifact ebpy will not read."""
    _write_v1_baseline(tmp_path)
    _write_v1_state(tmp_path)
    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "invalid"
    assert "ebpy freeze --force" in invalid_artifacts_message(artifacts)


def test_this_repositorys_own_artifacts_are_version_two_and_agree() -> None:
    """The repository's own .ebpy/baseline.json and .ebpy/state.json must be version 2 and must
    classify as a valid frozen contract — the tool eats its own cooking."""
    repo_root = Path(__file__).resolve().parents[1]

    baseline_raw = json.loads((repo_root / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    state_raw = json.loads((repo_root / ".ebpy" / "state.json").read_text(encoding="utf-8"))

    assert baseline_raw.get("version") == 2
    assert state_raw.get("version") == 2

    artifacts = read_ceiling_artifacts(repo_root)
    assert artifacts.kind != "invalid"
