from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ebpy.models import RuleBaseline, State
from ebpy.state import (
    Ledger,
    append_log,
    apply_analyzer_rule_counts,
    empty_state,
    improvements,
    next_baseline,
    read_ledger,
    replace_analyzer_rules,
    state_from_dict,
    state_to_dict,
    total_violations,
    write_state,
)


def _v1_raw(
    *,
    rules: dict[str, Any] | None = None,
    counters: dict[str, Any] | None = None,
    log: list[dict[str, Any]] | None = None,
    frozen_at: str | None = None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "tool": "ebpy",
        "phase": "drain",
        "updatedAt": "2026-08-19T00:00:00Z",
        "frozenAt": frozen_at,
        "diagnosedAt": None,
        "diagnosedCommit": None,
        "diagnosis": None,
        "rules": rules or {},
        "counters": counters or {},
        "log": log or [],
    }


def _v2_raw(
    *,
    frozen_analyzers: list[str] | None = None,
    rules: dict[str, Any] | None = None,
    log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "version": 2,
        "tool": "ebpy",
        "phase": "drain",
        "updatedAt": "2026-08-19T00:00:00Z",
        "frozenAt": "2026-08-19T00:00:00Z",
        "diagnosedAt": None,
        "diagnosedCommit": None,
        "diagnosis": None,
        "frozenAnalyzers": frozen_analyzers if frozen_analyzers is not None else ["ruff"],
        "rules": rules or {},
        "log": log or [],
    }


def test_observe_leaves_the_ceiling_alone() -> None:
    assert next_baseline(10, 12, "observe") == 10
    assert next_baseline(10, 3, "observe") == 10


def test_freeze_lowers_but_never_raises() -> None:
    assert next_baseline(10, 3, "freeze") == 3
    # Running freeze twice after a bad week must not legalise the damage.
    assert next_baseline(10, 42, "freeze") == 10


def test_rebaseline_is_the_only_way_up() -> None:
    assert next_baseline(10, 42, "rebaseline") == 42


def test_a_rule_seen_for_the_first_time_starts_at_todays_count() -> None:
    assert next_baseline(None, 7, "observe") == 7


def test_v1_rules_and_log_rules_are_read_as_ruff_namespaced() -> None:
    raw = _v1_raw(
        rules={"F401": {"baseline": 2, "current": 1, "status": "draining"}},
        log=[{"at": "2026-08-19T00:00:00Z", "kind": "note", "text": "seen", "rule": "C901"}],
    )

    state = state_from_dict(raw)

    assert state is not None
    assert "ruff:F401" in state.rules
    assert state.rules["ruff:F401"] == RuleBaseline(baseline=2, current=1, status="draining")
    assert state.log[0].rule == "ruff:C901"


def test_a_v1_current_above_its_baseline_is_clamped_rather_than_carried_over() -> None:
    raw = _v1_raw(rules={"F401": {"baseline": 2, "current": 5, "status": "draining"}})

    state = state_from_dict(raw)

    assert state is not None
    assert state.rules["ruff:F401"].current == 2


def test_a_v1_zero_mypy_counter_becomes_roster_membership_on_a_frozen_state() -> None:
    raw = _v1_raw(
        counters={"mypy:errors": {"baseline": 0, "current": 0}},
        frozen_at="2026-08-19T00:00:00Z",
    )

    state = state_from_dict(raw)

    assert state is not None
    assert "mypy" in state.frozen_analyzers
    assert "ruff" in state.frozen_analyzers


def test_a_v1_zero_mypy_counter_on_an_unfrozen_state_leaves_the_roster_empty() -> None:
    raw = _v1_raw(counters={"mypy:errors": {"baseline": 0, "current": 0}}, frozen_at=None)

    state = state_from_dict(raw)

    assert state is not None
    assert state.frozen_analyzers == ()


def test_a_v1_mypy_counter_with_a_nonzero_baseline_makes_the_state_unreadable() -> None:
    raw = _v1_raw(counters={"mypy:errors": {"baseline": 3, "current": 3}})

    assert state_from_dict(raw) is None


def test_a_v1_mypy_counter_with_a_nonzero_current_makes_the_state_unreadable() -> None:
    raw = _v1_raw(counters={"mypy:errors": {"baseline": 0, "current": 2}})

    assert state_from_dict(raw) is None


def test_a_v1_mypy_counter_that_improved_to_zero_still_makes_the_state_unreadable() -> None:
    # A scalar total that fell to zero this run still cannot be decomposed into the file x
    # rule cells v2 requires -- the nonzero baseline is what makes it unreadable, not the current.
    raw = _v1_raw(counters={"mypy:errors": {"baseline": 5, "current": 0}})

    assert state_from_dict(raw) is None


def test_a_v1_counter_of_an_unknown_name_makes_the_state_unreadable() -> None:
    raw = _v1_raw(counters={"other:thing": {"baseline": 0, "current": 0}})

    assert state_from_dict(raw) is None


def test_a_v2_state_carrying_counters_is_rejected() -> None:
    raw = _v2_raw()
    raw["counters"] = {}

    assert state_from_dict(raw) is None


def test_a_v2_rule_outside_the_frozen_roster_is_rejected() -> None:
    raw = _v2_raw(
        frozen_analyzers=["ruff"],
        rules={"mypy:arg-type": {"baseline": 1, "current": 1, "status": "draining"}},
    )

    assert state_from_dict(raw) is None


def test_a_v2_rule_whose_current_exceeds_its_baseline_is_rejected() -> None:
    raw = _v2_raw(rules={"ruff:F401": {"baseline": 1, "current": 2, "status": "draining"}})

    assert state_from_dict(raw) is None


def test_a_v2_log_entrys_rule_need_not_be_in_the_frozen_roster() -> None:
    # A rule can drain to nothing and leave the contract while its log entry -- e.g. the note
    # recording that it was drained -- stays behind, so the log's rule is checked for shape
    # only, never roster membership.
    raw = _v2_raw(
        frozen_analyzers=["ruff"],
        log=[
            {
                "at": "2026-08-19T00:00:00Z",
                "kind": "drained",
                "text": "mypy:arg-type fully drained",
                "rule": "mypy:arg-type",
            }
        ],
    )

    state = state_from_dict(raw)

    assert state is not None
    assert state.log[0].rule == "mypy:arg-type"


def test_apply_analyzer_rule_counts_zeroes_a_drained_rule_in_its_own_namespace() -> None:
    state = State(
        frozen_analyzers=("ruff",),
        rules={"ruff:F401": RuleBaseline(baseline=3, current=3, status="draining")},
    )

    result = apply_analyzer_rule_counts(state, "ruff", {}, "observe")

    assert result.rules["ruff:F401"] == RuleBaseline(baseline=3, current=0, status="enforced")


def test_apply_analyzer_rule_counts_leaves_another_analyzers_rules_untouched() -> None:
    state = State(
        frozen_analyzers=("ruff", "mypy"),
        rules={
            "ruff:F401": RuleBaseline(baseline=3, current=3, status="draining"),
            "mypy:arg-type": RuleBaseline(baseline=2, current=2, status="draining"),
        },
    )

    result = apply_analyzer_rule_counts(state, "ruff", {"ruff:F401": 1}, "observe")

    assert result.rules["mypy:arg-type"] == RuleBaseline(baseline=2, current=2, status="draining")


def test_apply_analyzer_rule_counts_gives_a_new_rule_its_first_baseline() -> None:
    state = State(frozen_analyzers=("ruff",), rules={})

    result = apply_analyzer_rule_counts(state, "ruff", {"ruff:F401": 4}, "freeze")

    assert result.rules["ruff:F401"] == RuleBaseline(baseline=4, current=4, status="draining")


def test_improvements_are_rules_below_their_ceiling() -> None:
    state = empty_state()
    state.frozen_analyzers = ("ruff",)
    state.rules = {
        "ruff:E501": RuleBaseline(baseline=5, current=2, status="draining"),
        "ruff:F401": RuleBaseline(baseline=1, current=1, status="draining"),
    }

    assert [item.name for item in improvements(state)] == ["ruff:E501"]
    assert total_violations(state) == 3


def test_replace_analyzer_rules_replaces_only_the_named_namespace() -> None:
    state = State(
        frozen_analyzers=("ruff", "mypy"),
        rules={
            "ruff:F401": RuleBaseline(baseline=5, current=5, status="draining"),
            "ruff:E501": RuleBaseline(baseline=9, current=9, status="draining"),
            "mypy:arg-type": RuleBaseline(baseline=2, current=2, status="draining"),
        },
    )

    result = replace_analyzer_rules(state, "ruff", {"ruff:F401": 0})

    assert result.rules == {
        "ruff:F401": RuleBaseline(baseline=0, current=0, status="enforced"),
        "mypy:arg-type": RuleBaseline(baseline=2, current=2, status="draining"),
    }


def test_reading_a_v1_state_leaves_the_file_untouched(tmp_path: Path) -> None:
    path = tmp_path / ".ebpy" / "state.json"
    path.parent.mkdir(parents=True)
    raw = _v1_raw(rules={"F401": {"baseline": 2, "current": 1, "status": "draining"}})
    original_bytes = (json.dumps(raw) + "\n").encode("utf-8")
    path.write_bytes(original_bytes)

    ledger = read_ledger(tmp_path)

    assert ledger.state is not None
    assert path.read_bytes() == original_bytes


def test_missing_state_reads_as_none(tmp_path: Path) -> None:
    assert read_ledger(tmp_path) == Ledger(exists=False, state=None)


def test_invalid_utf8_state_reads_as_none(tmp_path: Path) -> None:
    path = tmp_path / ".ebpy" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe")

    assert read_ledger(tmp_path) == Ledger(exists=True, state=None)


@pytest.mark.parametrize("target_exists", [False, True])
def test_a_state_symlink_is_always_unreadable(tmp_path: Path, target_exists: bool) -> None:
    target = tmp_path / "outside-state.json"
    if target_exists:
        target.write_text(
            '{"version": 2, "frozenAnalyzers": [], "rules": {}, "log": []}\n',
            encoding="utf-8",
        )
    path = tmp_path / ".ebpy" / "state.json"
    path.parent.mkdir(parents=True)
    path.symlink_to(target)

    assert read_ledger(tmp_path) == Ledger(exists=True, state=None)


def test_empty_state_is_not_frozen_of_any_analyzer() -> None:
    assert empty_state().frozen_analyzers == ()


def test_writing_and_reading_a_v2_state_round_trips(tmp_path: Path) -> None:
    state = replace_analyzer_rules(empty_state(), "ruff", {"ruff:F401": 3})
    state.frozen_analyzers = ("ruff",)
    write_state(tmp_path, state)

    loaded = read_ledger(tmp_path).state

    assert loaded is not None
    assert loaded.rules["ruff:F401"] == RuleBaseline(baseline=3, current=3, status="draining")
    assert loaded.frozen_analyzers == ("ruff",)


def test_the_writer_always_emits_version_two_with_a_sorted_roster() -> None:
    state = State(
        frozen_analyzers=("ruff", "mypy"),
        rules={
            "ruff:F401": RuleBaseline(baseline=2, current=1, status="draining"),
            "mypy:arg-type": RuleBaseline(baseline=1, current=1, status="draining"),
        },
    )

    raw = state_to_dict(state)

    assert raw["version"] == 2
    assert raw["frozenAnalyzers"] == ["mypy", "ruff"]
    assert list(raw["rules"]) == ["mypy:arg-type", "ruff:F401"]


def test_the_writer_emits_no_counters_key() -> None:
    raw = state_to_dict(empty_state())

    assert "counters" not in raw


@pytest.mark.parametrize(
    "raw",
    [
        {"version": 1, "rules": {"F401": "broken"}, "counters": {}},
        {"version": 2, "frozenAnalyzers": ["ruff"], "rules": {"ruff:F401": "broken"}},
    ],
    ids=["v1", "v2"],
)
def test_structurally_invalid_state_is_present_but_unreadable(tmp_path: Path, raw: dict[str, Any]) -> None:
    path = tmp_path / ".ebpy" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(raw), encoding="utf-8")

    assert read_ledger(tmp_path) == Ledger(exists=True, state=None)


def test_falsy_containers_with_the_wrong_type_are_not_valid_state() -> None:
    valid_v1 = {"version": 1, "rules": {}, "counters": {}, "log": []}
    for field, invalid in (("rules", []), ("counters", []), ("log", {})):
        assert state_from_dict({**valid_v1, field: invalid}) is None

    # frozenAnalyzers has no v1 counterpart: it is the new roster field the decomposed
    # `_valid_frozen_analyzers` shape check exists for.
    valid_v2 = {"version": 2, "frozenAnalyzers": [], "rules": {}, "log": []}
    for field, invalid in (("rules", []), ("frozenAnalyzers", {}), ("log", {})):
        assert state_from_dict({**valid_v2, field: invalid}) is None


def test_invalid_ceiling_fields_are_not_coerced_into_valid_state() -> None:
    valid_v1 = {"version": 1, "rules": {}, "counters": {}, "log": []}

    assert state_from_dict({**valid_v1, "phase": "unknown"}) is None
    assert state_from_dict({**valid_v1, "updatedAt": 42}) is None
    assert state_from_dict({**valid_v1, "frozenAt": ""}) is None
    # A bool is an int subclass in Python; `_is_count` must not let one masquerade as a count.
    assert (
        state_from_dict(
            {**valid_v1, "rules": {"F401": {"baseline": True, "current": 1, "status": "draining"}}}
        )
        is None
    )
    assert state_from_dict({**valid_v1, "counters": {"mypy:errors": {"baseline": -1, "current": 1}}}) is None

    valid_v2 = {"version": 2, "frozenAnalyzers": ["ruff"], "rules": {}, "log": []}

    assert state_from_dict({**valid_v2, "phase": "unknown"}) is None
    assert state_from_dict({**valid_v2, "updatedAt": 42}) is None
    assert state_from_dict({**valid_v2, "frozenAt": ""}) is None
    assert (
        state_from_dict(
            {**valid_v2, "rules": {"ruff:F401": {"baseline": True, "current": 1, "status": "draining"}}}
        )
        is None
    )
    # v2 has no scalar counters to carry a negative count; the equivalent case is a rule
    # whose own current has gone negative.
    assert (
        state_from_dict(
            {**valid_v2, "rules": {"ruff:F401": {"baseline": 1, "current": -1, "status": "draining"}}}
        )
        is None
    )


def test_a_log_cannot_grow_without_bound() -> None:
    state = empty_state()
    for index in range(250):
        state = append_log(state, "note", f"entry {index}", None)
    assert len(state.log) == 200
    assert state.log[-1].text == "entry 249"
