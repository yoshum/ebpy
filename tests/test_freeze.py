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
from ebpy.ruff_runner import RuffResult
from ebpy.state import state_path


@pytest.mark.parametrize("cells", [{}, {"src/app.py": {"F401": 1}}])
def test_freeze_refuses_a_baseline_without_its_ledger(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    cells: dict[str, dict[str, int]],
) -> None:
    """Losing `.ebpy/state.json` is ordinary: every command rewrites it, so a merge
    conflict is enough. A freeze that re-pinned today's counts because of it would
    grandfather everything added since."""
    write_cells(tmp_path, cells)
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")

    assert main(["--cwd", str(tmp_path), "freeze"]) == 1

    output = capsys.readouterr().out
    assert "--force" in output
    assert "state.json" in output
    assert "prune" not in output
    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before
    assert not state_path(tmp_path).exists()


def test_force_replaces_an_invalid_pair_with_a_complete_new_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_cells(tmp_path, {"src/old.py": {"F401": 1}})
    monkeypatch.setattr(freeze, "run_ruff_check", lambda _cwd: RuffResult(cells={}))
    monkeypatch.setattr(freeze, "run_mypy_error_count", lambda _cwd: None)
    monkeypatch.setattr(freeze, "write_quality_file", lambda _cwd, _state: None)

    run_freeze(tmp_path, force=True)

    assert read_ceiling_artifacts(tmp_path).kind == "frozen"


def test_force_replaces_artifact_symlinks_without_touching_their_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_target = tmp_path / "outside-baseline.json"
    state_target = tmp_path / "outside-state.json"
    baseline_text = "{}\n"
    state_text = '{"version": 1, "rules": {}, "counters": {}, "log": []}\n'
    baseline_target.write_text(baseline_text, encoding="utf-8")
    state_target.write_text(state_text, encoding="utf-8")

    artifact_dir = tmp_path / ".ebpy"
    artifact_dir.mkdir()
    baseline_path(tmp_path).symlink_to(baseline_target)
    state_path(tmp_path).symlink_to(state_target)
    assert read_ceiling_artifacts(tmp_path).kind == "invalid"

    monkeypatch.setattr(freeze, "run_ruff_check", lambda _cwd: RuffResult(cells={}))
    monkeypatch.setattr(freeze, "run_mypy_error_count", lambda _cwd: None)
    monkeypatch.setattr(freeze, "write_quality_file", lambda _cwd, _state: None)

    run_freeze(tmp_path, force=True)

    assert not baseline_path(tmp_path).is_symlink()
    assert not state_path(tmp_path).is_symlink()
    assert baseline_target.read_text(encoding="utf-8") == baseline_text
    assert state_target.read_text(encoding="utf-8") == state_text
    assert read_ceiling_artifacts(tmp_path).kind == "frozen"


def test_force_replaces_a_symlinked_artifact_directory_without_touching_its_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside-artifacts"
    outside.mkdir()
    baseline_text = "{}\n"
    state_text = '{"version": 1, "rules": {}, "counters": {}, "log": []}\n'
    (outside / "baseline.json").write_text(baseline_text, encoding="utf-8")
    (outside / "state.json").write_text(state_text, encoding="utf-8")
    (tmp_path / ".ebpy").symlink_to(outside, target_is_directory=True)
    assert read_ceiling_artifacts(tmp_path).kind == "invalid"

    monkeypatch.setattr(freeze, "run_ruff_check", lambda _cwd: RuffResult(cells={}))
    monkeypatch.setattr(freeze, "run_mypy_error_count", lambda _cwd: None)
    monkeypatch.setattr(freeze, "write_quality_file", lambda _cwd, _state: None)

    run_freeze(tmp_path, force=True)

    assert not (tmp_path / ".ebpy").is_symlink()
    assert (outside / "baseline.json").read_text(encoding="utf-8") == baseline_text
    assert (outside / "state.json").read_text(encoding="utf-8") == state_text
    assert read_ceiling_artifacts(tmp_path).kind == "frozen"
