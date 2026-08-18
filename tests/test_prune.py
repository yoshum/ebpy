"""What `prune` refuses.

`prune` is documented as safe to run at any point, because it can only ever
lower a cell. That claim holds only for the cells clamped by the baseline file;
the ceilings for plain counters live in the ledger and have nothing to clamp
against, so a prune without a ledger would pin today's counts instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.baseline import BASELINE_FILE, baseline_path, write_cells
from ebpy.commands.prune import run_prune
from ebpy.errors import CommandError
from ebpy.state import empty_state, state_path, write_state


def test_prune_refuses_when_the_ledger_is_missing(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"F401": 1}})
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")

    with pytest.raises(CommandError, match=r"state\.json"):
        run_prune(tmp_path)

    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before
    assert not state_path(tmp_path).exists()


def test_prune_before_the_first_freeze_writes_nothing(tmp_path: Path) -> None:
    """`diagnose --write` and `log` both create a valid ledger before freeze. Its mere
    existence must not let prune create `{}`, which freeze would mistake for a ceiling
    pinned on a clean tree."""
    write_state(tmp_path, empty_state())
    state_before = state_path(tmp_path).read_text(encoding="utf-8")

    with pytest.raises(CommandError, match="freeze"):
        run_prune(tmp_path)

    assert not baseline_path(tmp_path).exists()
    assert state_path(tmp_path).read_text(encoding="utf-8") == state_before
