"""`ebpy check`: what fails the ratchet gate, what it persists, and how it reports each analyzer."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ebpy.commands import check as check_command
from ebpy.commands.check import check_measurement, run_check
from ebpy.measurement import Failed, Measured, Measurement, Unavailable
from ebpy.models import (
    AnalysisMeasurement,
    CellCounts,
    CiCoverage,
    Diagnosis,
    RuleBaseline,
    SizeDistribution,
    State,
    ToolSetup,
    UnmeasuredScope,
)
from ebpy.store.baseline import write_cells
from ebpy.store.state import read_ledger, write_state
from ebpy.tools.mypy import MypySetup

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _state(
    *,
    frozen_analyzers: tuple[str, ...] = ("ruff",),
    rules: dict[str, RuleBaseline] | None = None,
    diagnosis: Diagnosis | None = None,
) -> State:
    return State(frozen_analyzers=frozen_analyzers, rules=rules or {}, diagnosis=diagnosis)


def _measured(analyzer: str, cells: dict[str, dict[str, int]]) -> Measured[AnalysisMeasurement]:
    return Measured(tool=analyzer, value=AnalysisMeasurement(cells=cells))


def _diagnosis(*, mypy_configured: bool) -> Diagnosis:
    return Diagnosis(
        package_manager="uv",
        requires_python=None,
        framework="none",
        tool_setups={
            "ruff": ToolSetup(configured=True),
            "mypy": MypySetup(configured=mypy_configured, strict=False),
        },
        pre_commit=False,
        agent_instructions=(),
        ci=CiCoverage(
            present=False,
            runners=(),
            unpinned_actions=(),
            runs_lint=False,
            runs_typecheck=False,
            runs_test=False,
            runs_ebpy_check=False,
        ),
        sizes=SizeDistribution(total=0, over_file_limit=0, largest=()),
        gaps=(),
    )


def _write_frozen_pair(
    cwd: Path,
    cells: CellCounts | None = None,
    rules: dict[str, RuleBaseline] | None = None,
    *,
    frozen_analyzers: tuple[str, ...] = ("ruff",),
    unmeasured_packages: tuple[str, ...] = (),
) -> None:
    # A pyproject.toml so language detection evidences Python here — without it, an
    # unconfigured repository has no analyzer scope no matter what the ledger records.
    (cwd / "pyproject.toml").touch()
    write_cells(cwd, cells or {})
    state = State(
        frozen_analyzers=frozen_analyzers,
        rules=rules or {},
        frozen_at="2026-08-19T00:00:00Z",
        phase="drain",
        unmeasured_packages=unmeasured_packages,
    )
    write_state(cwd, state)


# --- Gate behaviour: a rule's first finding, wherever it lands -------------------------


def test_the_first_finding_of_a_new_rule_fails_for_ruff_and_for_mypy() -> None:
    previous = _state(frozen_analyzers=("mypy", "ruff"))
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {"src/a.py": {"ruff:F401": 1}}),
            "mypy": _measured("mypy", {"src/b.py": {"mypy:arg-type": 1}}),
        }
    )

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is False
    assert "ruff:F401" in decision.result.message
    assert "mypy:arg-type" in decision.result.message
    # Each analyzer's excess is reported on its own — one gating on the other's rule
    # would defeat the point of namespacing them.
    assert decision.result.message.count("finding(s) beyond the ceiling") == 2


def test_moving_a_mypy_error_between_files_fails_though_the_total_is_unchanged() -> None:
    previous = _state(frozen_analyzers=("mypy",))
    baseline: CellCounts = {"a.py": {"mypy:arg-type": 1}}
    measurement = Measurement(analyzers={"mypy": _measured("mypy", {"b.py": {"mypy:arg-type": 1}})})

    decision = check_measurement(previous, baseline, measurement)

    assert decision.result.ok is False
    assert "b.py" in decision.result.message
    assert "mypy:arg-type" in decision.result.message


def test_swapping_one_rule_for_another_inside_one_file_fails() -> None:
    previous = _state(frozen_analyzers=("mypy",))
    baseline: CellCounts = {"a.py": {"mypy:arg-type": 1}}
    measurement = Measurement(analyzers={"mypy": _measured("mypy", {"a.py": {"mypy:no-any-return": 1}})})

    decision = check_measurement(previous, baseline, measurement)

    assert decision.result.ok is False
    assert "a.py" in decision.result.message
    assert "mypy:no-any-return" in decision.result.message


def test_a_contract_analyzer_with_a_zero_ceiling_still_fails_when_it_cannot_be_measured() -> None:
    previous = _state(frozen_analyzers=("mypy",))
    measurement = Measurement(analyzers={"mypy": Unavailable(tool="mypy", detail="mypy is not installed")})

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is False
    assert "A ceiling nobody measured cannot be reported as held." in decision.result.message


# --- Analyzers outside the contract -----------------------------------------------------


def test_a_non_contract_analyzer_is_named_but_never_gates() -> None:
    previous = _state(frozen_analyzers=("ruff",))
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {}),
            "mypy": _measured("mypy", {"a.py": {"mypy:arg-type": 5}}),
        }
    )

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is True
    assert "mypy" in decision.result.message
    assert "not in the frozen contract" in decision.result.message


def test_check_stays_silent_about_a_configured_analyzer_that_did_not_run() -> None:
    """A configured-but-unrun analyzer goes unmentioned by check.

    The "configured but not ratcheted" advice moved to diagnose's gap; check speaks only about
    analyzers this run actually attempted.
    """
    previous = _state(frozen_analyzers=("ruff",), diagnosis=_diagnosis(mypy_configured=True))
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {})})

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is True
    assert "mypy" not in decision.result.message
    assert "configured in this repository" not in decision.result.message


def test_an_unavailable_non_contract_analyzer_is_named_as_unmeasured_not_as_configured() -> None:
    """An attempted but unavailable non-contract analyzer is reported as unmeasured.

    The standing "configured but not ratcheted" strand is diagnose's job, not check's.
    """
    previous = _state(frozen_analyzers=("ruff",), diagnosis=_diagnosis(mypy_configured=True))
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {}),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    decision = check_measurement(previous, {}, measurement)

    assert "mypy was not measured and has no ceiling here" in decision.result.message
    assert "configured in this repository" not in decision.result.message


def test_check_never_reconstructs_a_note_from_the_diagnosis() -> None:
    previous = _state(frozen_analyzers=("ruff",), diagnosis=None)
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {})})

    decision = check_measurement(previous, {}, measurement)

    assert "configured in this repository" not in decision.result.message


def test_a_configured_analyzer_that_ran_outside_the_contract_is_named_once() -> None:
    """A configured analyzer that ran outside the contract is named exactly once, not twice."""
    previous = _state(frozen_analyzers=("ruff",), diagnosis=_diagnosis(mypy_configured=True))
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {}),
            "mypy": _measured("mypy", {"a.py": {"mypy:arg-type": 5}}),
        }
    )

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is True
    assert decision.result.message.count("mypy ran but is not in the frozen contract") == 1
    assert decision.result.message.count("is configured in this repository") == 0
    # Freeze guidance is still present.
    assert "ebpy freeze --analyzer mypy" in decision.result.message


# --- Reporting shape: every failure, the worst cells, in order -------------------------


def test_every_failing_analyzer_is_reported_in_one_run_sorted_by_name() -> None:
    previous = _state(frozen_analyzers=("ruff", "mypy"))
    measurement = Measurement(
        analyzers={
            "mypy": Failed(tool="mypy", failure_kind="execution-failed", detail="mypy exploded"),
            "ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff exploded"),
        }
    )

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is False
    assert decision.result.message.index("mypy could not be measured") < decision.result.message.index(
        "ruff could not be measured"
    )


def test_the_excess_message_names_the_file_and_the_rule() -> None:
    previous = _state(frozen_analyzers=("mypy",))
    measurement = Measurement(analyzers={"mypy": _measured("mypy", {"src/widget.py": {"mypy:arg-type": 3}})})

    decision = check_measurement(previous, {}, measurement)

    assert "  src/widget.py  mypy:arg-type  +3" in decision.result.message


def test_the_excess_message_suggests_a_scoped_refreeze_for_that_analyzer() -> None:
    """The excess message suggests a scoped refreeze for that analyzer.

    A rule genuinely reconfigured is recovered by re-pinning only its analyzer. A global
    `freeze --force` would rebaseline every namespace, grandfathering unrelated analyzers'
    new violations, so the guidance names the analyzer and its scoped freeze.
    """
    previous = _state(frozen_analyzers=("mypy",))
    measurement = Measurement(analyzers={"mypy": _measured("mypy", {"src/widget.py": {"mypy:arg-type": 3}})})

    decision = check_measurement(previous, {}, measurement)

    assert "freeze --force --analyzer mypy" in decision.result.message


def test_a_mypy_error_cascading_into_untouched_files_names_each_of_them() -> None:
    previous = _state(frozen_analyzers=("mypy",))
    measurement = Measurement(
        analyzers={
            "mypy": _measured(
                "mypy",
                {
                    "src/a.py": {"mypy:arg-type": 1},
                    "src/b.py": {"mypy:arg-type": 1},
                    "src/c.py": {"mypy:arg-type": 1},
                },
            )
        }
    )

    decision = check_measurement(previous, {}, measurement)

    for file in ("src/a.py", "src/b.py", "src/c.py"):
        assert f"  {file}  mypy:arg-type  +1" in decision.result.message


# --- What survives into the ledger -------------------------------------------------------


def test_check_persists_only_held_counts_so_no_excess_survives_the_run() -> None:
    previous = _state(rules={"ruff:F401": RuleBaseline(baseline=1, current=1, status="draining")})
    baseline: CellCounts = {"a.py": {"ruff:F401": 1}}
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {"a.py": {"ruff:F401": 2}})})

    decision = check_measurement(previous, baseline, measurement)

    assert decision.result.ok is False
    assert decision.state.rules["ruff:F401"].current == 1


def test_a_complete_analyzer_is_persisted_even_when_another_analyzer_is_unverified() -> None:
    previous = _state(
        frozen_analyzers=("mypy", "ruff"),
        rules={"ruff:F401": RuleBaseline(baseline=2, current=2, status="draining")},
    )
    baseline: CellCounts = {"a.py": {"ruff:F401": 2}}
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {"a.py": {"ruff:F401": 1}}),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    decision = check_measurement(previous, baseline, measurement)

    assert decision.result.ok is False
    assert decision.state.rules["ruff:F401"].current == 1


def test_an_unverified_analyzer_keeps_its_previous_state_rules() -> None:
    previous = _state(
        frozen_analyzers=("mypy",),
        rules={"mypy:arg-type": RuleBaseline(baseline=4, current=4, status="draining")},
    )
    baseline: CellCounts = {"a.py": {"mypy:arg-type": 4}}
    measurement = Measurement(
        analyzers={"mypy": Failed(tool="mypy", failure_kind="execution-failed", detail="boom")}
    )

    decision = check_measurement(previous, baseline, measurement)

    assert decision.result.ok is False
    assert decision.state.rules["mypy:arg-type"] == RuleBaseline(baseline=4, current=4, status="draining")


def test_check_measurement_does_not_mutate_its_input_state_or_measurement() -> None:
    previous = _state(rules={"ruff:F401": RuleBaseline(baseline=3, current=3, status="draining")})
    original_rules = dict(previous.rules)
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {"a.py": {"ruff:F401": 1}})})
    original_analyzers = dict(measurement.analyzers)

    check_measurement(previous, {"a.py": {"ruff:F401": 3}}, measurement)

    assert previous.rules == original_rules
    assert measurement.analyzers == original_analyzers


# --- The write=False shell never touches disk -------------------------------------------


def test_no_write_persists_nothing_on_success_or_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_frozen_pair(
        tmp_path,
        {"a.py": {"ruff:F401": 1}},
        {"ruff:F401": RuleBaseline(baseline=1, current=1, status="draining")},
    )
    writes: list[str] = []
    monkeypatch.setattr(check_command, "write_state", lambda _cwd, _state: writes.append("state"))
    monkeypatch.setattr(check_command, "write_quality_file", lambda _cwd, _state: writes.append("quality"))

    monkeypatch.setattr(
        check_command,
        "measure_repository",
        lambda _cwd, _scope: Measurement(analyzers={"ruff": _measured("ruff", {"a.py": {"ruff:F401": 1}})}),
    )
    passing = run_check(tmp_path, write=False)
    assert passing.ok is True
    assert writes == []

    monkeypatch.setattr(
        check_command,
        "measure_repository",
        lambda _cwd, _scope: Measurement(analyzers={"ruff": _measured("ruff", {"a.py": {"ruff:F401": 5}})}),
    )
    failing = run_check(tmp_path, write=False)
    assert failing.ok is False
    assert writes == []


def test_a_contract_analyzer_with_no_runner_in_this_build_fails_closed() -> None:
    """A contract analyzer with no runner in this build fails closed.

    A frozen analyzer whose name this ebpy build has no runner for must fail closed: the
    ceiling is real but unverifiable, so the gate must not report it as held.
    """
    previous = _state(frozen_analyzers=("pylint",))
    measurement = Measurement(analyzers={})

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is False
    assert "pylint has no runner in this ebpy build" in decision.result.message
    assert "A ceiling nobody measured cannot be reported as held." in decision.result.message


def test_a_failed_analyzer_produces_an_unverified_failure_and_still_returns_state() -> None:
    """A failed analyzer produces an unverified failure and still returns state.

    A failed analyzer still produces a usable state so a complete neighbour's progress
    is not lost: `check_measurement` always returns state regardless of individual failures.
    """
    previous = _state(frozen_analyzers=("ruff",))
    measurement = Measurement(
        analyzers={"ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff failed")}
    )

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is False
    assert "ruff failed" in decision.result.message
    assert decision.state.rules == {}


def test_an_unmeasured_mypy_leaves_its_ceiling_untouched_while_ruff_is_still_applied() -> None:
    """An unmeasured mypy leaves its ceiling untouched while ruff is still applied.

    The gate refuses when one contract analyzer cannot be measured, while a sibling
    analyzer's measurement is still applied to the ledger rather than withheld.
    """
    previous = _state(
        frozen_analyzers=("mypy", "ruff"),
        rules={"mypy:arg-type": RuleBaseline(baseline=4, current=4, status="draining")},
    )
    baseline: CellCounts = {"a.py": {"ruff:F401": 1}, "b.py": {"mypy:arg-type": 4}}
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {"a.py": {"ruff:F401": 1}}),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    decision = check_measurement(previous, baseline, measurement)

    assert decision.result.ok is False
    assert decision.state.rules["mypy:arg-type"] == RuleBaseline(baseline=4, current=4, status="draining")
    assert decision.state.rules["ruff:F401"] == RuleBaseline(baseline=1, current=1, status="draining")


def test_check_rejects_cells_beyond_the_ceiling() -> None:
    """Check rejects cells beyond the ceiling.

    A cell beyond its ceiling fails the gate; the ledger records only the within-ceiling
    count, keyed by a namespaced rule id.
    """
    previous = _state(frozen_analyzers=("ruff",))
    baseline: CellCounts = {"src/a.py": {"ruff:F401": 1}}
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {"src/a.py": {"ruff:F401": 2}})})

    decision = check_measurement(previous, baseline, measurement)

    assert decision.result.ok is False
    assert "1 finding(s) beyond the ceiling" in decision.result.message
    assert decision.state.rules["ruff:F401"].current == 1


def test_check_shell_persists_state_and_quality_even_after_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check shell persists state and quality even after a failure.

    run_check must persist state and QUALITY.md on `write=True` even when the result is a
    failure, so a complete analyzer's progress is not lost to a neighbour's failure.
    """
    _write_frozen_pair(
        tmp_path,
        {"a.py": {"ruff:F401": 1}},
        {"ruff:F401": RuleBaseline(baseline=1, current=1, status="draining")},
    )
    measurement = Measurement(
        analyzers={"ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff failed")}
    )
    writes: list[str] = []
    monkeypatch.setattr(check_command, "measure_repository", lambda _cwd, _scope: measurement)
    monkeypatch.setattr(check_command, "write_state", lambda _cwd, _state: writes.append("state"))
    monkeypatch.setattr(check_command, "write_quality_file", lambda _cwd, _state: writes.append("quality"))

    result = run_check(tmp_path, write=True)

    assert not result.ok
    assert writes == ["state", "quality"]


def test_an_unmeasured_analyzer_reports_the_tools_detail_and_keeps_its_ceiling_unverified() -> None:
    """An unmeasured analyzer reports the tool's detail and keeps its ceiling unverified.

    An unmeasured contract analyzer quotes the tool's own failure detail and leaves its
    ceiling rules exactly as they were in the previous state.
    """
    previous = _state(
        frozen_analyzers=("mypy",),
        rules={"mypy:arg-type": RuleBaseline(baseline=4, current=4, status="draining")},
    )
    measurement = Measurement(
        analyzers={
            "mypy": Failed(
                tool="mypy",
                failure_kind="execution-failed",
                detail="mypy failed (exit 2): mypy.ini: [mypy]: Unrecognized option",
            )
        }
    )

    decision = check_measurement(previous, {"a.py": {"mypy:arg-type": 4}}, measurement)

    assert decision.result.ok is False
    assert "went unverified" in decision.result.message
    assert "Unrecognized option" in decision.result.message
    assert decision.state.rules["mypy:arg-type"] == RuleBaseline(baseline=4, current=4, status="draining")


def test_mypy_with_no_ceiling_passes_but_is_never_silent() -> None:
    """Mypy with no ceiling passes but is never silent.

    An analyzer outside the contract that could not be measured is still named in a clean
    run's message and never silently dropped.
    """
    previous = _state(frozen_analyzers=("ruff",))
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {}),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed here"),
        }
    )

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is True
    assert "mypy was not measured and has no ceiling here" in decision.result.message


def test_a_clean_run_leaves_the_message_unadorned() -> None:
    """A clean run leaves the message unadorned.

    A clean run with no notes produces exactly the summary line and nothing more — no
    stray separators or trailing whitespace.
    """
    previous = _state(frozen_analyzers=("ruff",))
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {})})

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is True
    assert decision.result.message == "Clean. 0 grandfathered findings left to drain across 1 analyzer."


def test_the_clean_summary_pluralizes_the_analyzer_count() -> None:
    """One analyzer reads "1 analyzer", more than one reads "2 analyzers"."""
    previous = _state(frozen_analyzers=("mypy", "ruff"))
    measurement = Measurement(analyzers={"mypy": _measured("mypy", {}), "ruff": _measured("ruff", {})})

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.message == "Clean. 0 grandfathered findings left to drain across 2 analyzers."


# --- Reconciliation gate (config.json vs frozen roster) ---------------------------------


def test_check_fails_when_declared_set_diverges_from_roster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check fails when the declared set diverges from the roster.

    run_check fails closed before measurement when config.json names a smaller analyzer
    set than the frozen roster — proof: the message contains only reconcile text and the
    measure_repository stub is never invoked.
    """
    write_cells(tmp_path, {"a.py": {"ruff:F401": 1}})
    write_state(
        tmp_path,
        State(
            frozen_analyzers=("mypy", "ruff"),
            rules={"ruff:F401": RuleBaseline(baseline=1, current=1, status="draining")},
            frozen_at="2026-08-19T00:00:00Z",
            phase="drain",
        ),
    )
    (tmp_path / ".ebpy" / "config.json").write_text(
        json.dumps({"version": 1, "analyzers": ["ruff"]}), encoding="utf-8"
    )

    measured: list[bool] = []

    def _no_measure(_cwd: Path, _scope: tuple[str, ...]) -> Measurement:
        measured.append(True)
        return Measurement(analyzers={})

    monkeypatch.setattr(check_command, "measure_repository", _no_measure)

    result = run_check(tmp_path, write=False)

    assert result.ok is False
    assert ".ebpy/config.json and the frozen contract disagree on the analyzer set:" in result.message
    assert "frozen but not declared: mypy" in result.message
    assert measured == []  # measurement was never invoked


def test_check_proceeds_normally_when_config_matches_frozen_roster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_check proceeds to measurement when config.json declares exactly the frozen analyzer set."""
    write_cells(tmp_path, {"a.py": {"ruff:F401": 1}})
    write_state(
        tmp_path,
        State(
            frozen_analyzers=("ruff",),
            rules={"ruff:F401": RuleBaseline(baseline=1, current=1, status="draining")},
            frozen_at="2026-08-19T00:00:00Z",
            phase="drain",
        ),
    )
    (tmp_path / ".ebpy" / "config.json").write_text(
        json.dumps({"version": 1, "analyzers": ["ruff"]}), encoding="utf-8"
    )
    monkeypatch.setattr(
        check_command,
        "measure_repository",
        lambda _cwd, _scope: Measurement(analyzers={"ruff": _measured("ruff", {"a.py": {"ruff:F401": 1}})}),
    )

    result = run_check(tmp_path, write=False)

    assert result.ok is True
    assert "Clean." in result.message


def test_check_refuses_before_measuring_when_the_contract_names_an_undetected_analyzer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reconciling before measuring is what keeps a skipped analyzer from becoming `no-runner`."""
    _write_frozen_pair(tmp_path, {}, {}, frozen_analyzers=("ruff", "clippy"))
    (tmp_path / ".ebpy" / "config.json").write_text(
        json.dumps({"version": 1, "analyzers": ["ruff"]}), encoding="utf-8"
    )

    def _never(_cwd: Path, _scope: tuple[str, ...]) -> Measurement:
        raise AssertionError("check must refuse before measuring")

    monkeypatch.setattr(check_command, "measure_repository", _never)
    result = check_command.run_check(tmp_path, write=False)
    assert not result.ok
    assert "clippy" in result.message


# --- A package leaving the ceiling's coverage fails closed ------------------------------


def test_check_refuses_when_a_workspace_that_held_a_ceiling_stops_compiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Written with a fixture that has no cells at all: a cell-based rule would pass here."""
    # A Cargo.toml puts clippy in this repository's analyzer scope; without it the run
    # would refuse on a scope mismatch before ever reaching the new coverage check.
    (tmp_path / "Cargo.toml").touch()
    _write_frozen_pair(tmp_path, frozen_analyzers=("clippy",), cells={})
    measurement = Measurement(
        {
            "clippy": Measured(
                tool="clippy",
                value=AnalysisMeasurement(
                    cells={}, unmeasured=(UnmeasuredScope(root=".", packages=("core",)),)
                ),
            )
        }
    )
    monkeypatch.setattr(check_command, "measure_repository", lambda _cwd, _scope: measurement)
    result = check_command.run_check(tmp_path, write=False)
    assert not result.ok
    assert "core" in result.message
    assert "freeze --force" in result.message


def test_check_records_a_widened_contract_so_a_second_break_is_still_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If only freeze and prune wrote the key, breaking it a second time would pass silently."""
    (tmp_path / "Cargo.toml").touch()
    _write_frozen_pair(tmp_path, frozen_analyzers=("clippy",), cells={}, unmeasured_packages=("fuzz",))
    measurement = Measurement({"clippy": Measured(tool="clippy", value=AnalysisMeasurement(cells={}))})
    monkeypatch.setattr(check_command, "measure_repository", lambda _cwd, _scope: measurement)
    assert check_command.run_check(tmp_path, write=True).ok
    state = read_ledger(tmp_path).state
    assert state is not None
    assert state.unmeasured_packages == ()


def test_a_failing_check_persists_state_without_emptying_the_unmeasured_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Persisting the state and replacing this key are different events."""
    (tmp_path / "Cargo.toml").touch()
    _write_frozen_pair(tmp_path, frozen_analyzers=("clippy",), cells={}, unmeasured_packages=("fuzz",))
    measurement = Measurement(
        {"clippy": Failed(tool="clippy", failure_kind="execution-failed", detail="boom")}
    )
    monkeypatch.setattr(check_command, "measure_repository", lambda _cwd, _scope: measurement)
    assert not check_command.run_check(tmp_path, write=True).ok
    state = read_ledger(tmp_path).state
    assert state is not None
    assert state.unmeasured_packages == ("fuzz",)
