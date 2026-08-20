"""What `freeze` does, what it refuses, and on what evidence.

Artifact-precondition checks happen before any measurement, so a repository
that must not be frozen cannot have its ceiling raised by the run that discovers it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.cli import main
from ebpy.commands import freeze
from ebpy.commands.freeze import freeze_measurement, run_freeze
from ebpy.errors import CommandError
from ebpy.measurement import Failed, Measured, Measurement, Unavailable
from ebpy.models import AnalysisMeasurement, UnattributedFinding
from ebpy.store.baseline import BASELINE_FILE, baseline_path, write_cells
from ebpy.store.ceiling_artifacts import CeilingArtifacts, read_ceiling_artifacts
from ebpy.store.state import Ledger, apply_analyzer_rule_counts, empty_state, state_path, with_phase

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FROZEN_AT = "2026-08-19T00:00:00Z"


def _both_analyzers_measurement(cells: dict[str, dict[str, int]] | None = None) -> Measurement:
    """Both analyzers complete; cells defaults to empty for a clean zero-finding contract."""
    return Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells=cells or {}),
            ),
            "mypy": Measured(
                tool="mypy",
                value=AnalysisMeasurement(cells={}),
            ),
        }
    )


def _fresh_artifacts() -> CeilingArtifacts:
    return CeilingArtifacts(kind="fresh", cells={}, ledger=Ledger(exists=False, state=None))


def _frozen_artifacts_ruff_only() -> CeilingArtifacts:
    """A valid frozen pair that contains only ruff (simulates a v1-migrated contract)."""
    cells: dict[str, dict[str, int]] = {"src/a.py": {"ruff:F401": 1}}
    state = empty_state()
    state = apply_analyzer_rule_counts(state, "ruff", {"ruff:F401": 1}, "freeze")
    state.frozen_at = _FROZEN_AT
    state.frozen_analyzers = ("ruff",)
    state = with_phase(state, "drain")
    return CeilingArtifacts(kind="frozen", cells=cells, ledger=Ledger(exists=True, state=state))


# ---------------------------------------------------------------------------
# Write-safety / symlink tests (original tests adapted to the new model)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cells", [{}, {"src/app.py": {"ruff:F401": 1}}])
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
    write_cells(tmp_path, {"src/old.py": {"ruff:F401": 1}})
    monkeypatch.setattr(freeze, "measure_repository", lambda _cwd: _both_analyzers_measurement())
    monkeypatch.setattr(freeze, "write_quality_file", lambda _cwd, _state: None)

    run_freeze(tmp_path, force=True, analyzer=None)

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

    monkeypatch.setattr(freeze, "measure_repository", lambda _cwd: _both_analyzers_measurement())
    monkeypatch.setattr(freeze, "write_quality_file", lambda _cwd, _state: None)

    run_freeze(tmp_path, force=True, analyzer=None)

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

    monkeypatch.setattr(freeze, "measure_repository", lambda _cwd: _both_analyzers_measurement())
    monkeypatch.setattr(freeze, "write_quality_file", lambda _cwd, _state: None)

    run_freeze(tmp_path, force=True, analyzer=None)

    assert not (tmp_path / ".ebpy").is_symlink()
    assert (outside / "baseline.json").read_text(encoding="utf-8") == baseline_text
    assert (outside / "state.json").read_text(encoding="utf-8") == state_text
    assert read_ceiling_artifacts(tmp_path).kind == "frozen"


def test_forcing_does_not_strip_the_ledger_it_read_from_disk() -> None:
    """`--force` clears rules to pin a new contract — on its own copy, not the on-disk state.
    The roster is preserved so the forced freeze still covers every analyzer the old contract
    named rather than dropping one it cannot measure."""
    on_disk = apply_analyzer_rule_counts(empty_state(), "ruff", {"ruff:F401": 2}, "freeze")
    on_disk.frozen_analyzers = ("ruff",)
    artifacts = CeilingArtifacts(kind="frozen", cells={}, ledger=Ledger(exists=True, state=on_disk))

    previous = freeze._previous_state(artifacts, force=True)

    assert previous.rules == {}
    assert previous.frozen_analyzers == ("ruff",)
    assert on_disk.rules["ruff:F401"].baseline == 2
    assert on_disk.frozen_analyzers == ("ruff",)


# ---------------------------------------------------------------------------
# 18 new tests (verbatim names from the brief)
# ---------------------------------------------------------------------------


def test_a_first_freeze_records_every_analyzer_including_a_clean_one() -> None:
    decision = freeze_measurement(
        empty_state(),
        {},
        Measurement(
            analyzers={
                "ruff": Measured(
                    tool="ruff",
                    value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 2}}),
                ),
                "mypy": Measured(
                    tool="mypy",
                    value=AnalysisMeasurement(cells={}),
                ),
            }
        ),
        scope=None,
        force=False,
        frozen_at=_FROZEN_AT,
    )

    assert set(decision.state.frozen_analyzers) == {"ruff", "mypy"}
    assert "ruff:F401" in decision.state.rules
    assert decision.state.frozen_at == _FROZEN_AT
    # mypy with zero findings joins the roster — a 0 ceiling is only verifiable
    # if we know mypy actually ran and found nothing.
    assert "mypy" in decision.state.frozen_analyzers
    assert decision.cells == {"src/a.py": {"ruff:F401": 2}}


def test_an_incomplete_analyzer_refuses_a_normal_freeze_and_writes_nothing() -> None:
    incomplete_ruff = Measured(
        tool="ruff",
        value=AnalysisMeasurement(
            cells={},
            unattributed=(UnattributedFinding(file="src/bad.py", line=1, message="SyntaxError"),),
        ),
    )
    measurement = Measurement(
        analyzers={
            "ruff": incomplete_ruff,
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
        }
    )

    with pytest.raises(CommandError) as exc_info:
        freeze_measurement(empty_state(), {}, measurement, scope=None, force=False, frozen_at=_FROZEN_AT)

    assert "Nothing was written" in str(exc_info.value)


def test_the_incomplete_refusal_names_fixing_the_file_and_the_analyzers_exclude() -> None:
    incomplete_ruff = Measured(
        tool="ruff",
        value=AnalysisMeasurement(
            cells={},
            unattributed=(UnattributedFinding(file="src/bad.py", line=1, message="SyntaxError"),),
        ),
    )
    measurement = Measurement(
        analyzers={
            "ruff": incomplete_ruff,
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
        }
    )

    with pytest.raises(CommandError) as exc_info:
        freeze_measurement(empty_state(), {}, measurement, scope=None, force=False, frozen_at=_FROZEN_AT)

    msg = str(exc_info.value)
    assert "exclude" in msg
    assert "src/bad.py" in msg


def test_an_incomplete_mypy_refusal_does_not_tell_the_user_to_edit_ruff() -> None:
    """The refusal and unattributed remediation were generalized to any analyzer, so a
    mypy syntax error must not tell the user to edit Ruff's exclude — the advice names the
    analyzer that actually could not parse the file."""
    incomplete_mypy = Measured(
        tool="mypy",
        value=AnalysisMeasurement(
            cells={},
            unattributed=(UnattributedFinding(file="src/bad.py", line=1, message="SyntaxError"),),
        ),
    )
    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            "mypy": incomplete_mypy,
        }
    )

    with pytest.raises(CommandError) as exc_info:
        freeze_measurement(empty_state(), {}, measurement, scope=None, force=False, frozen_at=_FROZEN_AT)

    msg = str(exc_info.value)
    assert "Ruff" not in msg and "ruff's" not in msg.lower()
    assert "mypy" in msg


def test_an_unavailable_analyzer_refuses_a_normal_freeze_and_names_bootstrap() -> None:
    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    with pytest.raises(CommandError) as exc_info:
        freeze_measurement(empty_state(), {}, measurement, scope=None, force=False, frozen_at=_FROZEN_AT)

    assert "bootstrap" in str(exc_info.value)
    assert "Nothing was written" in str(exc_info.value)


def test_a_failed_analyzer_refuses_a_normal_freeze_and_quotes_its_detail() -> None:
    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            "mypy": Failed(tool="mypy", failure_kind="execution-failed", detail="mypy crashed: exit 2"),
        }
    )

    with pytest.raises(CommandError) as exc_info:
        freeze_measurement(empty_state(), {}, measurement, scope=None, force=False, frozen_at=_FROZEN_AT)

    assert "mypy crashed: exit 2" in str(exc_info.value)
    assert "Nothing was written" in str(exc_info.value)


def test_force_refuses_an_unavailable_analyzer_because_force_never_shrinks_the_contract() -> None:
    """--force re-pins every analyzer's ceiling; an unavailable one is still refused."""
    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    with pytest.raises(CommandError) as exc_info:
        freeze_measurement(empty_state(), {}, measurement, scope=None, force=True, frozen_at=_FROZEN_AT)

    assert "Nothing was written" in str(exc_info.value)


def test_a_global_freeze_refuses_to_drop_a_rostered_analyzer_this_build_cannot_measure() -> None:
    """A contract may name an analyzer a newer ebpy froze but this build has no runner for.
    A global freeze must not silently drop it — that would break "no invocation removes an
    analyzer" — so an unmeasurable rostered analyzer fails the freeze closed."""
    previous = apply_analyzer_rule_counts(empty_state(), "ruff", {"ruff:F401": 1}, "freeze")
    previous.frozen_analyzers = ("pylint", "ruff")
    previous.frozen_at = _FROZEN_AT

    with pytest.raises(CommandError) as exc_info:
        freeze_measurement(
            previous, {}, _both_analyzers_measurement(), scope=None, force=True, frozen_at=_FROZEN_AT
        )

    message = str(exc_info.value)
    assert "pylint" in message
    assert "Nothing was written" in message


def test_a_global_freeze_re_pins_every_rostered_analyzer_it_can_measure() -> None:
    """When every rostered analyzer is measurable, a forced global freeze keeps the full
    roster rather than narrowing it to this build's default set."""
    previous = apply_analyzer_rule_counts(empty_state(), "ruff", {"ruff:F401": 9}, "freeze")
    previous.frozen_analyzers = ("mypy", "ruff")
    previous.frozen_at = _FROZEN_AT

    decision = freeze_measurement(
        previous, {}, _both_analyzers_measurement(), scope=None, force=True, frozen_at=_FROZEN_AT
    )

    assert set(decision.state.frozen_analyzers) == {"ruff", "mypy"}


def test_force_refuses_an_incomplete_analyzer_too() -> None:
    incomplete_ruff = Measured(
        tool="ruff",
        value=AnalysisMeasurement(
            cells={},
            unattributed=(UnattributedFinding(file="src/bad.py", line=1, message="SyntaxError"),),
        ),
    )
    measurement = Measurement(
        analyzers={
            "ruff": incomplete_ruff,
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
        }
    )

    with pytest.raises(CommandError) as exc_info:
        freeze_measurement(empty_state(), {}, measurement, scope=None, force=True, frozen_at=_FROZEN_AT)

    assert "Nothing was written" in str(exc_info.value)


def test_the_unavailable_refusal_points_at_bootstrap() -> None:
    measurement = Measurement(
        analyzers={
            "ruff": Unavailable(tool="ruff", detail="ruff not found"),
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
        }
    )

    with pytest.raises(CommandError) as exc_info:
        freeze_measurement(empty_state(), {}, measurement, scope=None, force=False, frozen_at=_FROZEN_AT)

    assert "bootstrap" in str(exc_info.value)


def test_scoped_freeze_is_allowed_on_a_fresh_pair() -> None:
    """A fresh pair has no contract to preserve, so `freeze --analyzer NAME` is the
    staged-adoption path: it builds a narrow contract holding only NAME from the start."""
    artifacts = _fresh_artifacts()

    precondition = freeze._check_scope_preconditions(artifacts, "mypy", force=False)

    assert precondition is None


def test_scoped_freeze_on_a_fresh_pair_builds_a_narrow_contract() -> None:
    """The first freeze can be scoped: a repository whose toolchain is incomplete pins only
    the analyzer it can measure, stamping frozen_at and advancing to drain so the pair is a
    valid frozen contract — the narrow roster the check and render machinery expect."""
    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 2}}),
            ),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    decision = freeze_measurement(
        empty_state(),
        {},
        measurement,
        scope="ruff",
        force=False,
        frozen_at=_FROZEN_AT,
    )

    assert decision.state.frozen_analyzers == ("ruff",)
    assert "mypy" not in decision.state.frozen_analyzers
    assert decision.state.frozen_at == _FROZEN_AT
    assert decision.state.phase == "drain"
    assert decision.cells == {"src/a.py": {"ruff:F401": 2}}


def test_scoped_freeze_on_a_fresh_pair_yields_a_valid_frozen_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Driving the whole command on a fresh repository with `--analyzer` writes a pair that
    reads back as a valid frozen contract, not an invalid half-freeze."""
    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 1}}),
            ),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )
    monkeypatch.setattr(freeze, "measure_repository", lambda _cwd: measurement)
    monkeypatch.setattr(freeze, "write_quality_file", lambda _cwd, _state: None)

    run_freeze(tmp_path, force=False, analyzer="ruff")

    artifacts = read_ceiling_artifacts(tmp_path)
    assert artifacts.kind == "frozen"
    assert artifacts.ledger.state is not None
    assert artifacts.ledger.state.frozen_analyzers == ("ruff",)


def test_scoped_freeze_ignores_another_analyzers_failure() -> None:
    """freeze --force --analyzer ruff succeeds even when mypy failed."""
    artifacts = _frozen_artifacts_ruff_only()
    assert artifacts.ledger.state is not None

    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 1}}),
            ),
            "mypy": Failed(tool="mypy", failure_kind="execution-failed", detail="mypy crashed"),
        }
    )

    # ruff is already in the roster, so --force is required to replace it
    decision = freeze_measurement(
        artifacts.ledger.state,
        artifacts.cells,
        measurement,
        scope="ruff",
        force=True,
        frozen_at=_FROZEN_AT,
    )

    # mypy failure is irrelevant when scope is ruff
    assert "ruff:F401" in decision.state.rules


def test_scoped_freeze_adds_mypy_and_leaves_the_ruff_ceiling_identical() -> None:
    """freeze --analyzer mypy on a ruff-only contract extends the roster without touching ruff."""
    artifacts = _frozen_artifacts_ruff_only()
    assert artifacts.ledger.state is not None

    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 1}}),
            ),
            "mypy": Measured(
                tool="mypy", value=AnalysisMeasurement(cells={"src/b.py": {"mypy:arg-type": 3}})
            ),
        }
    )

    decision = freeze_measurement(
        artifacts.ledger.state,
        artifacts.cells,
        measurement,
        scope="mypy",
        force=False,
        frozen_at=_FROZEN_AT,
    )

    assert "mypy" in decision.state.frozen_analyzers
    assert "ruff" in decision.state.frozen_analyzers
    assert decision.state.rules["ruff:F401"].baseline == 1
    assert decision.state.rules["mypy:arg-type"].baseline == 3
    assert decision.cells == {"src/a.py": {"ruff:F401": 1}, "src/b.py": {"mypy:arg-type": 3}}


def test_scoped_force_replaces_only_the_named_namespace() -> None:
    """freeze --force --analyzer ruff replaces ruff cells; mypy cells are untouched."""
    state = empty_state()
    state = apply_analyzer_rule_counts(state, "ruff", {"ruff:F401": 5}, "freeze")
    state = apply_analyzer_rule_counts(state, "mypy", {"mypy:arg-type": 3}, "freeze")
    state.frozen_at = _FROZEN_AT
    state.frozen_analyzers = ("mypy", "ruff")
    state = with_phase(state, "drain")

    baseline_cells: dict[str, dict[str, int]] = {
        "src/a.py": {"ruff:F401": 5},
        "src/b.py": {"mypy:arg-type": 3},
    }
    artifacts = CeilingArtifacts(kind="frozen", cells=baseline_cells, ledger=Ledger(exists=True, state=state))
    assert artifacts.ledger.state is not None

    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 2}})),
            "mypy": Measured(
                tool="mypy", value=AnalysisMeasurement(cells={"src/b.py": {"mypy:arg-type": 3}})
            ),
        }
    )

    decision = freeze_measurement(
        artifacts.ledger.state,
        artifacts.cells,
        measurement,
        scope="ruff",
        force=True,
        frozen_at=_FROZEN_AT,
    )

    assert decision.state.rules["ruff:F401"].baseline == 2
    assert decision.state.rules["mypy:arg-type"].baseline == 3
    assert decision.cells == {"src/a.py": {"ruff:F401": 2}, "src/b.py": {"mypy:arg-type": 3}}


def test_a_scoped_freeze_of_a_new_analyzer_says_it_was_added() -> None:
    """Adding an analyzer not yet in the roster grows the contract, so the verb is "added"."""
    artifacts = _frozen_artifacts_ruff_only()
    assert artifacts.ledger.state is not None

    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 1}})),
            "mypy": Measured(
                tool="mypy", value=AnalysisMeasurement(cells={"src/b.py": {"mypy:arg-type": 3}})
            ),
        }
    )

    decision = freeze_measurement(
        artifacts.ledger.state,
        artifacts.cells,
        measurement,
        scope="mypy",
        force=False,
        frozen_at=_FROZEN_AT,
    )

    assert "added to the ceiling" in decision.message
    assert "replaced" not in decision.message


def test_a_scoped_re_pin_says_it_replaced_rather_than_added() -> None:
    """--force --analyzer on an analyzer already in the roster replaces its namespace; the
    message must not claim it was "added", which would misdescribe a re-pin."""
    artifacts = _frozen_artifacts_ruff_only()
    assert artifacts.ledger.state is not None

    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 2}})),
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
        }
    )

    decision = freeze_measurement(
        artifacts.ledger.state,
        artifacts.cells,
        measurement,
        scope="ruff",
        force=True,
        frozen_at=_FROZEN_AT,
    )

    assert "replaced" in decision.message
    assert "added to the ceiling" not in decision.message


def test_a_scoped_re_pin_of_an_all_clean_analyzer_reports_zero_violations() -> None:
    """Re-pinning an analyzer that now measures clean grandfathers nothing; the totals must
    reflect the measured namespace, not report a phantom rule."""
    artifacts = _frozen_artifacts_ruff_only()
    assert artifacts.ledger.state is not None

    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
        }
    )

    decision = freeze_measurement(
        artifacts.ledger.state,
        artifacts.cells,
        measurement,
        scope="ruff",
        force=True,
        frozen_at=_FROZEN_AT,
    )

    assert "0 violations across 0 rules" in decision.message
    assert "replaced" in decision.message


def test_scoped_freeze_refuses_an_analyzer_already_in_the_contract() -> None:
    artifacts = _frozen_artifacts_ruff_only()

    # ruff is already in the roster; adding it again without --force is refused
    precondition = freeze._check_scope_preconditions(artifacts, "ruff", force=False)

    assert precondition is not None
    assert "already" in precondition
    assert "--force" in precondition


def test_scoped_freeze_refuses_a_target_that_is_not_complete() -> None:
    artifacts = _frozen_artifacts_ruff_only()
    assert artifacts.ledger.state is not None

    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={})),
            "mypy": Unavailable(tool="mypy", detail="mypy not installed"),
        }
    )

    with pytest.raises(CommandError) as exc_info:
        freeze_measurement(
            artifacts.ledger.state,
            artifacts.cells,
            measurement,
            scope="mypy",
            force=False,
            frozen_at=_FROZEN_AT,
        )

    assert "Nothing was written" in str(exc_info.value)


def test_scoped_freeze_refuses_an_invalid_pair_even_with_force() -> None:
    artifacts = CeilingArtifacts(
        kind="invalid",
        cells={},
        ledger=Ledger(exists=True, state=None),
        detail="baseline and state disagree",
    )

    precondition = freeze._check_scope_preconditions(artifacts, "mypy", force=True)

    assert precondition is not None


def test_scoped_freeze_keeps_the_global_frozen_at() -> None:
    """A scoped freeze extends the roster but does not reset the global frozen_at."""
    artifacts = _frozen_artifacts_ruff_only()
    assert artifacts.ledger.state is not None
    original_frozen_at = artifacts.ledger.state.frozen_at

    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 1}})),
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
        }
    )

    decision = freeze_measurement(
        artifacts.ledger.state,
        artifacts.cells,
        measurement,
        scope="mypy",
        force=False,
        frozen_at="2026-09-01T00:00:00Z",  # a later timestamp — must not overwrite frozen_at
    )

    assert decision.state.frozen_at == original_frozen_at


def test_no_invocation_can_remove_an_analyzer_from_the_roster() -> None:
    """A scoped --force replaces one namespace but must not drop the other from the roster."""
    state = empty_state()
    state = apply_analyzer_rule_counts(state, "ruff", {"ruff:F401": 1}, "freeze")
    state = apply_analyzer_rule_counts(state, "mypy", {"mypy:arg-type": 1}, "freeze")
    state.frozen_at = _FROZEN_AT
    state.frozen_analyzers = ("mypy", "ruff")
    state = with_phase(state, "drain")

    baseline_cells: dict[str, dict[str, int]] = {
        "src/a.py": {"ruff:F401": 1},
        "src/b.py": {"mypy:arg-type": 1},
    }
    artifacts = CeilingArtifacts(kind="frozen", cells=baseline_cells, ledger=Ledger(exists=True, state=state))
    assert artifacts.ledger.state is not None

    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 1}})),
            "mypy": Measured(
                tool="mypy", value=AnalysisMeasurement(cells={"src/b.py": {"mypy:arg-type": 1}})
            ),
        }
    )
    decision = freeze_measurement(
        artifacts.ledger.state,
        artifacts.cells,
        measurement,
        scope="ruff",
        force=True,
        frozen_at=_FROZEN_AT,
    )

    assert "mypy" in decision.state.frozen_analyzers
    assert "ruff" in decision.state.frozen_analyzers


def test_the_freeze_message_counts_distinct_rules_not_cells() -> None:
    """The 'across N rules' figure must be the count of distinct rule IDs, not
    the number of file x rule cell pairs.  A single rule appearing in multiple
    files is still one rule."""
    # F401 appears in two files (2 cells) and arg-type appears in one file —
    # that is 3 cells but only 2 distinct rules.
    measurement = Measurement(
        analyzers={
            "ruff": Measured(
                tool="ruff",
                value=AnalysisMeasurement(
                    cells={
                        "src/a.py": {"ruff:F401": 3},
                        "src/b.py": {"ruff:F401": 1},
                    }
                ),
            ),
            "mypy": Measured(
                tool="mypy",
                value=AnalysisMeasurement(cells={"src/c.py": {"mypy:arg-type": 2}}),
            ),
        }
    )

    decision = freeze_measurement(
        empty_state(), {}, measurement, scope=None, force=False, frozen_at=_FROZEN_AT
    )

    assert "across 2 rules" in decision.message


def test_freeze_measurement_does_not_mutate_its_input_state() -> None:
    original = empty_state()
    measurement = Measurement(
        analyzers={
            "ruff": Measured(tool="ruff", value=AnalysisMeasurement(cells={"src/a.py": {"ruff:F401": 1}})),
            "mypy": Measured(tool="mypy", value=AnalysisMeasurement(cells={})),
        }
    )

    freeze_measurement(original, {}, measurement, scope=None, force=False, frozen_at=_FROZEN_AT)

    assert original.frozen_at is None
    assert original.rules == {}
    assert original.frozen_analyzers == ()
