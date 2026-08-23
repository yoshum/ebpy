from __future__ import annotations

from pathlib import Path

import pytest

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
)
from ebpy.repo.detect.detector import MypySetup, ToolSetup
from ebpy.store.baseline import write_cells
from ebpy.store.state import write_state


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


def _write_frozen_ceiling(cwd: Path, cells: CellCounts, rules: dict[str, RuleBaseline]) -> None:
    write_cells(cwd, cells)
    state = State(frozen_analyzers=("ruff",), rules=rules, frozen_at="2026-08-19T00:00:00Z", phase="drain")
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


def test_an_analyzer_the_repo_configures_but_the_contract_omits_is_reported_every_run() -> None:
    previous = _state(frozen_analyzers=("ruff",), diagnosis=_diagnosis(mypy_configured=True))
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {})})

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is True
    assert (
        "mypy is configured in this repository but is not in the frozen contract." in decision.result.message
    )
    assert "ebpy freeze --analyzer mypy" in decision.result.message


def test_that_standing_note_appears_even_when_the_analyzer_could_not_run() -> None:
    previous = _state(frozen_analyzers=("ruff",), diagnosis=_diagnosis(mypy_configured=True))
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {}),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    decision = check_measurement(previous, {}, measurement)

    assert (
        "mypy is configured in this repository but is not in the frozen contract." in decision.result.message
    )


def test_no_standing_note_is_invented_when_the_repo_has_no_diagnosis() -> None:
    previous = _state(frozen_analyzers=("ruff",), diagnosis=None)
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {})})

    decision = check_measurement(previous, {}, measurement)

    assert "configured in this repository" not in decision.result.message


def test_a_configured_analyzer_that_ran_outside_the_contract_gets_one_merged_note() -> None:
    """The "it ran, so its findings are unratcheted" fact and the "it is configured, freeze
    puts it under the ceiling" fact are the same analyzer, so they collapse into a single
    paragraph rather than double-warning about mypy."""
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
    # The actionable freeze guidance still survives the merge.
    assert "ebpy freeze --analyzer mypy" in decision.result.message


def test_a_configured_analyzer_that_did_not_run_keeps_its_standing_note() -> None:
    previous = _state(frozen_analyzers=("ruff",), diagnosis=_diagnosis(mypy_configured=True))
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {}),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.message.count("is configured in this repository") == 1
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
    """A rule genuinely reconfigured is recovered by re-pinning only its analyzer. A global
    `freeze --force` would rebaseline every namespace, grandfathering unrelated analyzers'
    new violations, so the guidance names the analyzer and its scoped freeze."""
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
    _write_frozen_ceiling(
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
        lambda _cwd: Measurement(analyzers={"ruff": _measured("ruff", {"a.py": {"ruff:F401": 1}})}),
    )
    passing = run_check(tmp_path, write=False)
    assert passing.ok is True
    assert writes == []

    monkeypatch.setattr(
        check_command,
        "measure_repository",
        lambda _cwd: Measurement(analyzers={"ruff": _measured("ruff", {"a.py": {"ruff:F401": 5}})}),
    )
    failing = run_check(tmp_path, write=False)
    assert failing.ok is False
    assert writes == []


def test_a_contract_analyzer_with_no_runner_in_this_build_fails_closed() -> None:
    """A frozen analyzer whose name this ebpy build has no runner for must fail closed: the
    ceiling is real but unverifiable, so the gate must not report it as held."""
    previous = _state(frozen_analyzers=("pylint",))
    measurement = Measurement(analyzers={})

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is False
    assert "pylint has no runner in this ebpy build" in decision.result.message
    assert "A ceiling nobody measured cannot be reported as held." in decision.result.message


def test_a_failed_analyzer_produces_an_unverified_failure_and_still_returns_state() -> None:
    """A failed analyzer still produces a usable state so a complete neighbour's progress
    is not lost: `check_measurement` always returns state regardless of individual failures."""
    previous = _state(frozen_analyzers=("ruff",))
    measurement = Measurement(
        analyzers={"ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff failed")}
    )

    decision = check_measurement(previous, {}, measurement)

    assert decision.result.ok is False
    assert "ruff failed" in decision.result.message
    assert decision.state.rules == {}


def test_an_unmeasured_mypy_leaves_its_ceiling_untouched_while_ruff_is_still_applied() -> None:
    """The gate refuses when one contract analyzer cannot be measured, while a sibling
    analyzer's measurement is still applied to the ledger rather than withheld."""
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
    """A cell beyond its ceiling fails the gate; the ledger records only the within-ceiling
    count, keyed by a namespaced rule id."""
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
    """run_check must persist state and QUALITY.md on `write=True` even when the result is a
    failure, so a complete analyzer's progress is not lost to a neighbour's failure."""
    _write_frozen_ceiling(
        tmp_path,
        {"a.py": {"ruff:F401": 1}},
        {"ruff:F401": RuleBaseline(baseline=1, current=1, status="draining")},
    )
    measurement = Measurement(
        analyzers={"ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff failed")}
    )
    writes: list[str] = []
    monkeypatch.setattr(check_command, "measure_repository", lambda _cwd: measurement)
    monkeypatch.setattr(check_command, "write_state", lambda _cwd, _state: writes.append("state"))
    monkeypatch.setattr(check_command, "write_quality_file", lambda _cwd, _state: writes.append("quality"))

    result = run_check(tmp_path, write=True)

    assert not result.ok
    assert writes == ["state", "quality"]


def test_an_unmeasured_analyzer_reports_the_tools_detail_and_keeps_its_ceiling_unverified() -> None:
    """An unmeasured contract analyzer quotes the tool's own failure detail and leaves its
    ceiling rules exactly as they were in the previous state."""
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
    """An analyzer outside the contract that could not be measured is still named in a clean
    run's message and never silently dropped."""
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
    """A clean run with no notes produces exactly the summary line and nothing more — no
    stray separators or trailing whitespace."""
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
