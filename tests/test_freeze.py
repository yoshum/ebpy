"""What `freeze` refuses, and on what evidence.

None of these need Ruff: the refusal has to be decided before anything is
measured, or a repository whose ledger is unreadable would have its ceiling
raised by the very run that was supposed to protect it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.cli import main
from ebpy.commands import freeze
from ebpy.commands.freeze import freeze_measurement, run_freeze
from ebpy.errors import CommandError
from ebpy.measurement import Failed, Measured, Measurement, Unavailable
from ebpy.models import MYPY_COUNTER, LintMeasurement
from ebpy.persist.baseline import BASELINE_FILE, baseline_path, write_cells
from ebpy.persist.ceiling_artifacts import CeilingArtifacts, read_ceiling_artifacts
from ebpy.persist.state import Ledger, apply_rule_counts, empty_state, set_counter, state_path


def clean_measurement() -> Measurement:
    return Measurement(
        lint=Measured(tool="ruff", value=LintMeasurement(cells={})),
        counters={MYPY_COUNTER: Unavailable(tool="mypy", detail="mypy is not installed")},
    )


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
    monkeypatch.setattr(freeze, "measure_repository", lambda _cwd: clean_measurement())
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

    monkeypatch.setattr(freeze, "measure_repository", lambda _cwd: clean_measurement())
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

    monkeypatch.setattr(freeze, "measure_repository", lambda _cwd: clean_measurement())
    monkeypatch.setattr(freeze, "write_quality_file", lambda _cwd, _state: None)

    run_freeze(tmp_path, force=True)

    assert not (tmp_path / ".ebpy").is_symlink()
    assert (outside / "baseline.json").read_text(encoding="utf-8") == baseline_text
    assert (outside / "state.json").read_text(encoding="utf-8") == state_text
    assert read_ceiling_artifacts(tmp_path).kind == "frozen"


def test_failed_lint_cannot_build_a_frozen_contract() -> None:
    previous = empty_state()
    measurement = Measurement(
        lint=Failed(tool="ruff", failure_kind="execution-failed", detail="ruff failed"),
        counters={MYPY_COUNTER: Measured(tool="mypy", value=2)},
    )

    with pytest.raises(CommandError, match="ruff failed"):
        freeze_measurement(previous, measurement, "freeze", "2026-08-19T00:00:00Z")

    assert previous.frozen_at is None
    assert previous.counters == {}


def test_freeze_records_measured_values_and_names_an_unmeasured_counter() -> None:
    decision = freeze_measurement(
        empty_state(),
        Measurement(
            lint=Measured(
                tool="ruff",
                value=LintMeasurement(cells={"src/a.py": {"F401": 2}}),
            ),
            counters={MYPY_COUNTER: Unavailable(tool="mypy", detail="mypy is not installed.")},
        ),
        "freeze",
        "2026-08-19T00:00:00Z",
    )

    assert decision.cells == {"src/a.py": {"F401": 2}}
    assert decision.state.frozen_at == "2026-08-19T00:00:00Z"
    assert decision.state.rules["F401"].baseline == 2
    assert MYPY_COUNTER not in decision.state.counters
    assert "mypy did not run: mypy is not installed" in decision.message
    assert "installed.." not in decision.message


@pytest.mark.parametrize(
    "detail",
    ["mypy is not installed.", "mypy failed (exit 2): bad config:", "mypy could not run,"],
)
def test_a_tool_detail_is_punctuated_once_inside_our_sentence(detail: str) -> None:
    """Runners end a message however reads best alone; the sentence around it owns the stop."""
    decision = freeze_measurement(
        empty_state(),
        Measurement(
            lint=Measured(tool="ruff", value=LintMeasurement(cells={})),
            counters={MYPY_COUNTER: Failed(tool="mypy", failure_kind="execution-failed", detail=detail)},
        ),
        "freeze",
        "2026-08-19T00:00:00Z",
    )

    line = next(line for line in decision.message.splitlines() if line.startswith("mypy did not run"))
    assert line.endswith(". No type-error ceiling was recorded.")
    for stutter in ("..", ":.", ",."):
        assert stutter not in line


def test_forcing_does_not_strip_the_ledger_it_read_from_disk() -> None:
    """`--force` clears rules and counters to pin a new contract — on its own copy."""
    on_disk = set_counter(apply_rule_counts(empty_state(), {"F401": 2}, "freeze"), MYPY_COUNTER, 5, "freeze")
    artifacts = CeilingArtifacts(kind="frozen", cells={}, ledger=Ledger(exists=True, state=on_disk))

    previous = freeze._previous_state(artifacts, force=True)

    assert previous.rules == {}
    assert previous.counters == {}
    assert on_disk.rules["F401"].baseline == 2
    assert on_disk.counters[MYPY_COUNTER].baseline == 5
