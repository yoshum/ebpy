"""What `freeze` refuses, and on what evidence.

None of these need Ruff: the refusal has to be decided before anything is
measured, or a repository whose ledger is unreadable would have its ceiling
raised by the very run that was supposed to protect it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.baseline import BASELINE_FILE, baseline_path, write_cells
from ebpy.ceiling_artifacts import read_ceiling_artifacts
from ebpy.cli import main
from ebpy.commands import freeze
from ebpy.commands.freeze import run_freeze
from ebpy.models import Counter, RuleBaseline
from ebpy.ruff_runner import RuffResult
from ebpy.state import empty_state, state_path, write_state


def write_raw_baseline(cwd: Path, text: str) -> None:
    path = baseline_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def orphan_ledger(cwd: Path, text: str) -> None:
    path = state_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_freeze_leaves_the_ceiling_alone_when_the_ledger_is_missing(tmp_path: Path) -> None:
    """Losing `.ebpy/state.json` is ordinary: every command rewrites it, so a merge
    conflict is enough. A freeze that re-pinned today's counts because of it would
    grandfather everything added since."""
    write_cells(tmp_path, {"src/app.py": {"F401": 1}})
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")

    result = run_freeze(tmp_path, force=False)

    assert not result.ok
    assert "--force" in result.message
    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before


def test_freeze_leaves_an_empty_ceiling_alone_when_the_ledger_is_missing(tmp_path: Path) -> None:
    """The clean-tree freeze, which `write_cells` records as `{}`. It has to refuse for
    the same reason as any other ceiling."""
    write_cells(tmp_path, {})
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")

    result = run_freeze(tmp_path, force=False)

    assert not result.ok
    assert "--force" in result.message
    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before


def test_freeze_leaves_the_ceiling_alone_when_the_ledger_is_unreadable(tmp_path: Path) -> None:
    """Conflict markers make the ledger invalid JSON, which `read_state` reports the same
    way as a file that was never written. Neither may unlock a re-freeze."""
    write_cells(tmp_path, {"src/app.py": {"F401": 1}})
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")
    orphan_ledger(tmp_path, "<<<<<<< HEAD\n{}\n=======\n{}\n>>>>>>> other\n")

    result = run_freeze(tmp_path, force=False)

    assert not result.ok
    assert "--force" in result.message
    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before


def test_freeze_leaves_the_ceiling_alone_when_the_ledger_is_invalid_utf8(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"F401": 1}})
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")
    path = state_path(tmp_path)
    path.write_bytes(b"\xff\xfe")

    result = run_freeze(tmp_path, force=False)

    assert not result.ok
    assert "unreadable" in result.message
    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before
    assert path.read_bytes() == b"\xff\xfe"


def test_freeze_refuses_an_unreadable_ledger_even_when_the_baseline_is_missing(
    tmp_path: Path,
) -> None:
    """A missing baseline does not prove this is the first freeze when a ledger exists
    but cannot reveal whether it holds state-only counter ceilings."""
    path = state_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe")

    result = run_freeze(tmp_path, force=False)

    assert not result.ok
    assert "state.json" in result.message
    assert not baseline_path(tmp_path).exists()
    assert path.read_bytes() == b"\xff\xfe"


def test_freeze_refuses_a_readable_ledger_with_ceiling_data_but_no_freeze(tmp_path: Path) -> None:
    """A partially repaired ledger is not a fresh one. Counts without ``frozenAt`` are
    evidence of a broken pair, not data from which freeze should reconstruct intent."""
    state = empty_state()
    state.rules = {"F401": RuleBaseline(baseline=1, current=1, status="draining")}
    state.counters = {"mypy:errors": Counter(baseline=1, current=1)}
    write_state(tmp_path, state)
    before = state_path(tmp_path).read_text(encoding="utf-8")

    result = run_freeze(tmp_path, force=False)

    assert not result.ok
    assert "invalid" in result.message
    assert "--force" in result.message
    assert not baseline_path(tmp_path).exists()
    assert state_path(tmp_path).read_text(encoding="utf-8") == before


def test_freeze_leaves_an_unreadable_ceiling_alone(tmp_path: Path) -> None:
    """Both ratchet files corrupted at once — the merge that conflicted in one of them
    can conflict in both."""
    write_raw_baseline(tmp_path, "<<<<<<< HEAD\n{}\n=======\n{}\n>>>>>>> other\n")
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")

    result = run_freeze(tmp_path, force=False)

    assert not result.ok
    assert "--force" in result.message
    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before


def test_the_refusal_sends_the_reader_to_the_ledger_not_to_prune(tmp_path: Path) -> None:
    """`prune` cannot rebuild this. Ruff cells are clamped by the baseline file, but the
    ceilings for counters such as mypy errors exist only in the ledger, so a prune
    started from an empty one would pin today's counts as their ceiling."""
    write_cells(tmp_path, {"src/app.py": {"F401": 1}})

    result = run_freeze(tmp_path, force=False)

    assert not result.ok
    assert "state.json" in result.message
    assert "prune" not in result.message


def test_freeze_refusal_exits_nonzero(tmp_path: Path) -> None:
    write_cells(tmp_path, {})

    assert main(["--cwd", str(tmp_path), "freeze"]) == 1


def test_force_replaces_an_invalid_pair_with_a_complete_new_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_cells(tmp_path, {"src/old.py": {"F401": 1}})
    monkeypatch.setattr(freeze, "run_ruff_check", lambda _cwd: RuffResult(cells={}))
    monkeypatch.setattr(freeze, "run_mypy_error_count", lambda _cwd: None)
    monkeypatch.setattr(freeze, "write_quality_file", lambda _cwd, _state: None)

    result = run_freeze(tmp_path, force=True)

    assert result.ok
    assert read_ceiling_artifacts(tmp_path).kind == "frozen"
