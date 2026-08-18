"""What `prune` refuses.

`prune` is documented as safe to run at any point, because it can only ever
lower a cell. That claim holds only for the cells clamped by the baseline file;
the ceilings for plain counters live in the ledger and have nothing to clamp
against, so a prune without a ledger would pin today's counts instead.
"""

from __future__ import annotations

from pathlib import Path

from ebpy.baseline import BASELINE_FILE, baseline_path, write_cells
from ebpy.cli import main
from ebpy.commands.prune import run_prune
from ebpy.state import empty_state, state_path, write_state


def test_prune_refuses_when_the_ledger_is_missing(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"F401": 1}})
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")

    result = run_prune(tmp_path)

    assert not result.ok
    assert "state.json" in result.message
    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before


def test_prune_refuses_when_the_ledger_is_unreadable(tmp_path: Path) -> None:
    """Conflict markers are the ordinary way this happens: every command rewrites the
    ledger, so two branches that both ran `ebpy check` conflict in it."""
    write_cells(tmp_path, {"src/app.py": {"F401": 1}})
    path = state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<<<<<<< HEAD\n{}\n=======\n{}\n>>>>>>> other\n", encoding="utf-8")

    result = run_prune(tmp_path)

    assert not result.ok
    assert "state.json" in result.message


def test_prune_refuses_when_the_ledger_is_invalid_utf8(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"F401": 1}})
    path = state_path(tmp_path)
    path.write_bytes(b"\xff\xfe")
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")

    result = run_prune(tmp_path)

    assert not result.ok
    assert "state.json" in result.message
    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before
    assert path.read_bytes() == b"\xff\xfe"


def test_the_refusal_writes_no_counter_ceiling(tmp_path: Path) -> None:
    """The failure this prevents: `set_counter` in `freeze` mode takes today's count as
    the ceiling when no previous one exists, so a prune started from an empty ledger
    would launder a mypy regression into a clean gate."""
    write_cells(tmp_path, {"src/app.py": {"F401": 1}})

    run_prune(tmp_path)

    assert not state_path(tmp_path).exists()


def test_prune_before_the_first_freeze_writes_nothing(tmp_path: Path) -> None:
    """`diagnose --write` and `log` both create a valid ledger before freeze. Its mere
    existence must not let prune create `{}`, which freeze would mistake for a ceiling
    pinned on a clean tree."""
    write_state(tmp_path, empty_state())
    state_before = state_path(tmp_path).read_text(encoding="utf-8")

    result = run_prune(tmp_path)

    assert not result.ok
    assert "freeze" in result.message
    assert not baseline_path(tmp_path).exists()
    assert state_path(tmp_path).read_text(encoding="utf-8") == state_before


def test_prune_refuses_when_a_frozen_ledger_has_no_baseline(tmp_path: Path) -> None:
    """Neither artifact can reconstruct the other: a ledger alone has no per-file cells."""
    state = empty_state()
    state.frozen_at = "2026-08-19T00:00:00Z"
    write_state(tmp_path, state)

    result = run_prune(tmp_path)

    assert not result.ok
    assert "baseline.json" in result.message
    assert not baseline_path(tmp_path).exists()


def test_prune_leaves_an_undecodable_baseline_untouched(tmp_path: Path) -> None:
    state = empty_state()
    state.frozen_at = "2026-08-19T00:00:00Z"
    write_state(tmp_path, state)
    path = baseline_path(tmp_path)
    path.write_bytes(b"\xff\xfe")
    before = path.read_bytes()

    result = run_prune(tmp_path)

    assert not result.ok
    assert "unreadable" in result.message
    assert path.read_bytes() == before


def test_prune_refusal_exits_nonzero(tmp_path: Path) -> None:
    assert main(["--cwd", str(tmp_path), "prune"]) == 1
