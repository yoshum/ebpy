"""`ebpy next`: refusing `--fan-in` where there is no Python to resolve imports from."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ebpy.commands.next_command import run_next
from ebpy.errors import CommandError
from ebpy.models import CellCounts, RuleBaseline, State
from ebpy.store.baseline import rule_totals, write_cells
from ebpy.store.state import write_state

if TYPE_CHECKING:
    from pathlib import Path


def _write_frozen_pair(cwd: Path, *, frozen_analyzers: tuple[str, ...], cells: CellCounts) -> None:
    # No pyproject.toml here: unlike the other commands' `_write_frozen_pair`, this file's
    # tests exist to prove behaviour in a repository with no Python evidence at all.
    write_cells(cwd, cells)
    state = State(
        frozen_analyzers=frozen_analyzers,
        rules={
            rule: RuleBaseline(baseline=count, current=count, status="draining")
            for rule, count in rule_totals(cells).items()
        },
        frozen_at="2026-08-19T00:00:00Z",
        phase="drain",
    )
    write_state(cwd, state)


def test_next_with_fan_in_refuses_a_repository_with_no_python(tmp_path: Path) -> None:
    """The importer graph resolves Python imports; without Python it is silently empty."""
    _write_frozen_pair(tmp_path, frozen_analyzers=("clippy",), cells={"src/lib.rs": {"clippy:x": 1}})
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    with pytest.raises(CommandError):
        run_next(tmp_path, as_json=False, fan_in=True)


def test_next_without_fan_in_still_works_on_a_rust_repository(tmp_path: Path) -> None:
    """It ranks from ceiling cells alone, which are language-independent."""
    _write_frozen_pair(tmp_path, frozen_analyzers=("clippy",), cells={"src/lib.rs": {"clippy:x": 1}})
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert run_next(tmp_path, as_json=False, fan_in=False)


def test_next_with_fan_in_runs_at_the_entry_point_on_a_python_repository(tmp_path: Path) -> None:
    """Pins the guard to a real `run_next(..., fan_in=True)` call, the only path that reaches it.

    `run_next(..., fan_in=True)` is otherwise called nowhere else in the suite — so an inverted
    guard condition would refuse this call unconditionally and no other test would catch it.
    """
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "util.py").write_text("def helper() -> None: ...\n", encoding="utf-8")
    (tmp_path / "pkg" / "a.py").write_text("from pkg.util import helper\n", encoding="utf-8")
    _write_frozen_pair(tmp_path, frozen_analyzers=("ruff",), cells={"pkg/util.py": {"ruff:F401": 3}})
    rendered = run_next(tmp_path, as_json=False, fan_in=True)
    assert "imported by 1" in rendered
