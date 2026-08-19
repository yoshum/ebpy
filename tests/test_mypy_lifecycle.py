"""End to end, against a real repository with both Ruff and mypy: the ratchet's
"can fall, never rise" claim must hold for mypy cells, not only ruff cells.

Each test stands alone: it builds its own fixture repo and drives the CLI through
a complete lifecycle sub-arc. Tests are slow because they spawn real processes;
keep fixtures minimal — one or two tiny source files — so each stays fast.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from ebpy.baseline import read_ceiling, write_cells
from ebpy.cli import main
from ebpy.models import RuleBaseline, State
from ebpy.state import write_state

pytestmark = pytest.mark.skipif(
    shutil.which("ruff") is None or shutil.which("mypy") is None,
    reason="needs real ruff and mypy on PATH",
)

# ---------------------------------------------------------------------------
# Source-file templates
# ---------------------------------------------------------------------------

# A file that gives ruff an F401 (unused import) AND gives mypy a type assignment
# mismatch that becomes `mypy:assignment`.  Using a deliberately wrong annotation on
# the call site is the most stable way to get [assignment] across mypy versions.
DIRTY_BOTH = """\
import os  # ruff:F401 — unused import


def add(a: int, b: int) -> int:
    return a + b


result: str = add(1, 2)  # mypy:assignment — assigning int to str
"""

# A clean version of the same file: no unused import, no type mismatch.
CLEAN = """\
def add(a: int, b: int) -> int:
    return a + b


result: int = add(1, 2)
"""

# A file carrying only the mypy error (no ruff violation), used to test that moving
# an error to a different file breaks the per-file ratchet.
MYPY_ONLY_FILE = """\
def add(a: int, b: int) -> int:
    return a + b


result: str = add(1, 2)  # mypy:assignment
"""

# A file carrying only the ruff violation, so both analyzers have findings during freeze.
RUFF_ONLY_FILE = """\
import os  # ruff:F401


def helper() -> None:
    pass
"""

# A syntactically invalid file: causes an "incomplete" measurement, blocking freeze.
UNPARSEABLE = "def f(:\n"

# A pyproject.toml that activates both ruff and strict mypy from the start.
_PYPROJECT = """\
[project]
name = "app"
version = "0.1.0"
requires-python = ">=3.11"

[tool.ruff]
select = ["F", "E"]

[tool.mypy]
strict = true
"""

_V1_FROZEN_AT = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def run(repo: Path, *args: str) -> int:
    return main(["--cwd", str(repo), *args])


def _init_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    return tmp_path


def _write_ruff_only_v2_artifacts(repo: Path) -> None:
    """Write a frozen v2 artifact pair covering only the ruff namespace.

    The normal CLI cannot produce a ruff-only contract because ANALYZER_NAMES always
    includes mypy; this helper simulates the state that results from migrating a v1
    artifact pair that had no mypy:errors counter.
    """
    ruff_cells: dict[str, dict[str, int]] = {"src/app.py": {"ruff:F401": 1}}
    write_cells(repo, ruff_cells)
    state = State(
        phase="drain",
        frozen_at=_V1_FROZEN_AT,
        frozen_analyzers=("ruff",),
        rules={"ruff:F401": RuleBaseline(baseline=1, current=1, status="draining")},
    )
    write_state(repo, state)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_freeze_records_both_namespaces_and_check_then_passes(tmp_path: Path) -> None:
    """freeze writes cells for both ruff: and mypy: namespaces; subsequent check == 0."""
    repo = _init_repo(tmp_path)
    (repo / "src" / "app.py").write_text(DIRTY_BOTH, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "initial")

    assert run(repo, "freeze") == 0

    baseline = json.loads((repo / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    cells: dict[str, Any] = baseline["cells"].get("src/app.py", {})
    ruff_keys = [k for k in cells if k.startswith("ruff:")]
    mypy_keys = [k for k in cells if k.startswith("mypy:")]
    assert ruff_keys, "expected at least one ruff: cell in baseline"
    assert mypy_keys, "expected at least one mypy: cell in baseline"

    # Today's findings exactly match the ceiling, so the gate must pass.
    assert run(repo, "check") == 0


def test_moving_a_mypy_error_to_another_file_fails_check(tmp_path: Path) -> None:
    """After freeze, moving the mypy error to a new file fails check (per-file ratchet)."""
    repo = _init_repo(tmp_path)
    # Put the mypy error in app.py and the ruff error in helper.py so both analyzers
    # produce findings for freeze (each in a separate file, no overlap).
    (repo / "src" / "app.py").write_text(MYPY_ONLY_FILE, encoding="utf-8")
    (repo / "src" / "helper.py").write_text(RUFF_ONLY_FILE, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "initial")

    assert run(repo, "freeze") == 0

    # Move the mypy error from app.py to a brand-new file (other.py).
    # app.py becomes clean; other.py has no cell of its own in the ceiling.
    (repo / "src" / "app.py").write_text(CLEAN, encoding="utf-8")
    (repo / "src" / "other.py").write_text(MYPY_ONLY_FILE, encoding="utf-8")

    assert run(repo, "check") == 1


def test_fixing_a_mypy_error_and_pruning_lowers_its_cell(tmp_path: Path) -> None:
    """Fixing the mypy error and running prune removes the mypy cell from baseline.json."""
    repo = _init_repo(tmp_path)
    (repo / "src" / "app.py").write_text(DIRTY_BOTH, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "initial")

    assert run(repo, "freeze") == 0

    # Confirm the mypy cell existed before the fix.
    before = json.loads((repo / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    assert any(k.startswith("mypy:") for k in before["cells"].get("src/app.py", {}))

    # Fix the file: no more unused import, no more type mismatch.
    (repo / "src" / "app.py").write_text(CLEAN, encoding="utf-8")
    assert run(repo, "prune") == 0

    after = json.loads((repo / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    remaining_mypy = [k for k in after["cells"].get("src/app.py", {}) if k.startswith("mypy:")]
    assert not remaining_mypy, "mypy cells should be gone after fixing the type error and pruning"


def test_reintroducing_the_same_error_fails_check_again(tmp_path: Path) -> None:
    """After prune reclaims the mypy ceiling, reintroducing the same error fails check."""
    repo = _init_repo(tmp_path)
    (repo / "src" / "app.py").write_text(DIRTY_BOTH, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "initial")

    assert run(repo, "freeze") == 0

    # Fix and prune to reclaim the ceiling.
    (repo / "src" / "app.py").write_text(CLEAN, encoding="utf-8")
    assert run(repo, "prune") == 0

    # Reintroduce the exact same type error: the reclaimed ceiling must hold.
    (repo / "src" / "app.py").write_text(DIRTY_BOTH, encoding="utf-8")
    assert run(repo, "check") == 1


def test_a_ruff_only_contract_accepts_a_scoped_mypy_freeze_without_moving_ruff_cells(
    tmp_path: Path,
) -> None:
    """freeze --analyzer mypy adds mypy cells without changing existing ruff cells."""
    repo = _init_repo(tmp_path)
    (repo / "src" / "app.py").write_text(DIRTY_BOTH, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "initial")

    # The CLI cannot produce a ruff-only contract because ANALYZER_NAMES always includes
    # mypy; write the artifacts directly (same shape a migrated v1 pair would produce).
    _write_ruff_only_v2_artifacts(repo)

    # Snapshot the ruff cells before the scoped freeze.
    before: dict[str, Any] = json.loads((repo / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    ruff_cells_before = {
        file: {k: v for k, v in rules.items() if k.startswith("ruff:")}
        for file, rules in before["cells"].items()
    }

    # Scoped mypy freeze must succeed and must not alter the ruff cells.
    assert run(repo, "freeze", "--analyzer", "mypy") == 0

    after: dict[str, Any] = json.loads((repo / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    ruff_cells_after = {
        file: {k: v for k, v in rules.items() if k.startswith("ruff:")}
        for file, rules in after["cells"].items()
    }
    mypy_cells_after = {
        file: {k: v for k, v in rules.items() if k.startswith("mypy:")}
        for file, rules in after["cells"].items()
        if any(k.startswith("mypy:") for k in rules)
    }

    assert ruff_cells_before == ruff_cells_after, "ruff cells must be byte-identical after scoped mypy freeze"
    assert mypy_cells_after, "expected at least one mypy: cell after scoped freeze"


def test_a_v1_pair_frozen_without_mypy_accepts_a_scoped_mypy_freeze(tmp_path: Path) -> None:
    """A migrated v1 contract (ruff-only roster) accepts freeze --analyzer mypy.

    v1 state gains "mypy" in its frozen_analyzers only when the counters dict carries a
    ``mypy:errors`` entry with {baseline: 0, current: 0}.  Omitting that counter migrates
    to frozen_analyzers == ("ruff",) — the precondition for scoped mypy freeze.
    """
    repo = _init_repo(tmp_path)
    (repo / "src" / "app.py").write_text(DIRTY_BOTH, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "initial")

    # Write a v1 artifact pair WITHOUT the mypy:errors counter: the migrated state will
    # have frozen_analyzers == ("ruff",), making this a ruff-only contract.
    v1_state: dict[str, Any] = {
        "version": 1,
        "tool": "ebpy",
        "phase": "drain",
        "updatedAt": _V1_FROZEN_AT,
        "frozenAt": _V1_FROZEN_AT,
        "diagnosedAt": None,
        "diagnosedCommit": None,
        "diagnosis": None,
        "rules": {"F401": {"baseline": 1, "current": 1, "status": "draining"}},
        "counters": {},
        "log": [],
    }
    # v1 baselines use bare (unnamespaced) rule keys.
    v1_baseline: dict[str, Any] = {"src/app.py": {"F401": {"count": 1}}}

    ebpy_dir = repo / ".ebpy"
    ebpy_dir.mkdir(parents=True, exist_ok=True)
    (ebpy_dir / "state.json").write_text(json.dumps(v1_state) + "\n", encoding="utf-8")
    (ebpy_dir / "baseline.json").write_text(json.dumps(v1_baseline) + "\n", encoding="utf-8")

    # Snapshot the ruff cells from the migrated baseline before the scoped freeze.
    # read_ceiling returns parsed counts as plain ints; compare using the same reader after.
    ceiling_before = read_ceiling(repo)
    assert ceiling_before.cells is not None
    ruff_cells_before = {
        file: {k: v for k, v in rules.items() if k.startswith("ruff:")}
        for file, rules in ceiling_before.cells.items()
    }

    # freeze --analyzer mypy must succeed on a ruff-only (v1-migrated) contract.
    assert run(repo, "freeze", "--analyzer", "mypy") == 0

    ceiling_after = read_ceiling(repo)
    assert ceiling_after.cells is not None
    ruff_cells_after = {
        file: {k: v for k, v in rules.items() if k.startswith("ruff:")}
        for file, rules in ceiling_after.cells.items()
    }
    mypy_cells_after = {
        file: {k: v for k, v in rules.items() if k.startswith("mypy:")}
        for file, rules in ceiling_after.cells.items()
        if any(k.startswith("mypy:") for k in rules)
    }

    assert ruff_cells_before == ruff_cells_after, "ruff cells must be unchanged after scoped mypy freeze"
    assert mypy_cells_after, "expected at least one mypy: cell after freeze --analyzer mypy"


def test_a_repository_with_an_unparseable_file_cannot_be_frozen_by_any_invocation(
    tmp_path: Path,
) -> None:
    """freeze and freeze --force both refuse when a file has a syntax error.

    A file that does not parse is invisible to every rule: recording a ceiling for it
    would be a lie.  Neither the global freeze nor the --force re-pin escape can write
    a trustworthy contract while the unparseable file remains.
    """
    repo = _init_repo(tmp_path)
    (repo / "src" / "app.py").write_text(DIRTY_BOTH, encoding="utf-8")
    (repo / "src" / "broken.py").write_text(UNPARSEABLE, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "initial")

    # Neither freeze variant must succeed.
    assert run(repo, "freeze") == 1
    assert run(repo, "freeze", "--force") == 1
    assert run(repo, "freeze", "--force", "--analyzer", "ruff") == 1

    # Nothing should have been written.
    assert not (repo / ".ebpy" / "baseline.json").exists()


def test_a_repository_without_mypy_installed_cannot_be_frozen_by_any_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """freeze and freeze --force both refuse when mypy is not installed.

    The suite's module-level skipif guard ensures mypy IS on PATH when the suite runs,
    so absence is simulated by monkeypatching ``find_mypy`` in ``ebpy.mypy_runner`` to
    return None — the same value it returns when no venv candidate and no PATH entry
    exist.  Patching the runner rather than ``shutil.which`` is more surgical: it leaves
    the ruff check unaffected and targets exactly the code path ``run_mypy_check`` calls.
    """
    repo = _init_repo(tmp_path)
    (repo / "src" / "app.py").write_text(DIRTY_BOTH, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "initial")

    monkeypatch.setattr("ebpy.mypy_runner.find_mypy", lambda _cwd: None)

    # Neither freeze nor force re-pin must succeed without mypy.
    assert run(repo, "freeze") == 1
    assert run(repo, "freeze", "--force") == 1

    # Nothing should have been written.
    assert not (repo / ".ebpy" / "baseline.json").exists()
