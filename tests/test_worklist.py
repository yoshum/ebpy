"""The worklist: when each phase counts as done, and how the smallest backlogs are ranked."""

from __future__ import annotations

from ebpy.decide.worklist import NEXT_RULES_SHOWN, build_worklist
from ebpy.models import (
    CiCoverage,
    Diagnosis,
    Gap,
    RuleBaseline,
    SizeDistribution,
    ToolSetup,
)
from ebpy.store.state import empty_state


def _diagnosis_with_gaps(*gaps: Gap) -> Diagnosis:
    return Diagnosis(
        package_manager="uv",
        requires_python=None,
        framework="none",
        tool_setups={"ruff": ToolSetup(configured=True)},
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
        gaps=gaps,
    )


def test_diagnose_is_done_once_the_ledger_records_when_it_was_taken() -> None:
    state = empty_state()
    assert not build_worklist(state).diagnosed
    state.diagnosed_at = "2026-08-01T00:00:00Z"
    verdict = build_worklist(state)
    assert verdict.diagnosed
    assert verdict.diagnosed_at == "2026-08-01T00:00:00Z"


def test_freeze_is_done_once_a_baseline_is_pinned() -> None:
    state = empty_state()
    assert not build_worklist(state).frozen
    state.frozen_at = "2026-08-02T00:00:00Z"
    verdict = build_worklist(state)
    assert verdict.frozen
    assert verdict.frozen_at == "2026-08-02T00:00:00Z"


def test_drain_is_done_only_once_the_backlog_is_empty() -> None:
    state = empty_state()
    state.frozen_at = "2026-08-02T00:00:00Z"
    assert build_worklist(state).drained
    state.rules = {"E501": RuleBaseline(baseline=3, current=3, status="draining")}
    verdict = build_worklist(state)
    assert not verdict.drained
    assert verdict.backlog == 3
    assert verdict.rule_count == 1


def test_drain_is_not_done_before_a_freeze_even_with_an_empty_backlog() -> None:
    # An empty backlog against no ceiling is "nobody drained anything", not "drained".
    verdict = build_worklist(empty_state())
    assert not verdict.drained


def test_smallest_backlogs_are_ranked_least_remaining_first_as_rule_count_pairs() -> None:
    state = empty_state()
    state.rules = {
        "E501": RuleBaseline(baseline=9, current=9, status="draining"),
        "F401": RuleBaseline(baseline=2, current=2, status="draining"),
        "clean": RuleBaseline(baseline=4, current=0, status="enforced"),
    }
    verdict = build_worklist(state)
    assert verdict.smallest_backlogs == (("F401", 2), ("E501", 9))


def test_smallest_backlogs_break_ties_on_equal_counts_by_rule_name() -> None:
    """Equal remaining counts sort by rule name, not dict insertion order."""
    state = empty_state()
    state.rules = {
        "F401": RuleBaseline(baseline=3, current=3, status="draining"),
        "B008": RuleBaseline(baseline=3, current=3, status="draining"),
        "E501": RuleBaseline(baseline=3, current=3, status="draining"),
    }
    verdict = build_worklist(state)
    assert verdict.smallest_backlogs == (("B008", 3), ("E501", 3), ("F401", 3))


def test_the_smallest_backlog_list_is_capped_at_the_number_of_rows_shown() -> None:
    state = empty_state()
    state.rules = {
        f"R{i:02d}": RuleBaseline(baseline=i + 1, current=i + 1, status="draining")
        for i in range(NEXT_RULES_SHOWN + 3)
    }
    verdict = build_worklist(state)
    assert len(verdict.smallest_backlogs) == NEXT_RULES_SHOWN


def test_bootstrap_is_done_only_after_a_diagnosis_closes_its_gaps() -> None:
    state = empty_state()
    # No diagnosis means bootstrap cannot be judged done, even with no gaps counted.
    assert not build_worklist(state).bootstrap_done
    state.diagnosed_at = "2026-08-01T00:00:00Z"
    assert build_worklist(state).bootstrap_done


def test_bootstrap_counts_only_the_gaps_that_belong_to_that_phase() -> None:
    state = empty_state()
    state.diagnosed_at = "2026-08-01T00:00:00Z"
    diagnosis = build_worklist(state)
    assert diagnosis.bootstrap_gaps == 0

    state.diagnosis = _diagnosis_with_gaps(
        Gap(id="a", title="", detail="", phase="bootstrap"),
        Gap(id="b", title="", detail="", phase="review"),
    )
    verdict = build_worklist(state)
    assert verdict.bootstrap_gaps == 1
    assert not verdict.bootstrap_done
