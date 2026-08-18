from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.models import Counter, RuleBaseline
from ebpy.state import (
    MYPY_COUNTER,
    Ledger,
    append_log,
    apply_rule_counts,
    empty_state,
    find_regressions,
    improvements,
    next_baseline,
    read_ledger,
    set_counter,
    state_from_dict,
    total_violations,
    write_state,
)


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


def test_apply_rule_counts_marks_a_cleared_rule_enforced() -> None:
    state = apply_rule_counts(empty_state(), {"E501": 3}, "freeze")
    assert state.rules["E501"].status == "draining"
    state = apply_rule_counts(state, {"E501": 0}, "observe")
    assert state.rules["E501"].status == "enforced"
    assert state.rules["E501"].baseline == 3


def test_a_rule_that_disappears_is_kept_at_zero_not_dropped() -> None:
    state = apply_rule_counts(empty_state(), {"E501": 3}, "freeze")
    state = apply_rule_counts(state, {}, "observe")
    assert state.rules["E501"].current == 0


def test_find_regressions_covers_rules_and_counters() -> None:
    state = empty_state()
    state.rules = {"E501": RuleBaseline(baseline=3, current=5, status="draining")}
    state.counters = {MYPY_COUNTER: Counter(baseline=2, current=9)}
    names = {item.name for item in find_regressions(state)}
    assert names == {"E501", MYPY_COUNTER}


def test_improvements_are_rules_below_their_ceiling() -> None:
    state = empty_state()
    state.rules = {
        "E501": RuleBaseline(baseline=5, current=2, status="draining"),
        "F401": RuleBaseline(baseline=1, current=1, status="draining"),
    }
    assert [item.name for item in improvements(state)] == ["E501"]
    assert total_violations(state) == 3


def test_state_round_trips_through_disk(tmp_path: Path) -> None:
    state = apply_rule_counts(empty_state(), {"E501": 4}, "freeze")
    state = set_counter(state, MYPY_COUNTER, 11, "freeze")
    state = append_log(state, "deferred", "router.py is 1400 lines", "abc1234", rule="PLR0915")
    write_state(tmp_path, state)

    loaded = read_ledger(tmp_path).state
    assert loaded is not None
    assert loaded.rules["E501"].baseline == 4
    assert loaded.counters[MYPY_COUNTER].current == 11
    assert loaded.log[0].kind == "deferred"
    assert loaded.log[0].rule == "PLR0915"
    assert loaded.log[0].commit == "abc1234"


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
            '{"version": 1, "rules": {}, "counters": {}, "log": []}\n',
            encoding="utf-8",
        )
    path = tmp_path / ".ebpy" / "state.json"
    path.parent.mkdir(parents=True)
    path.symlink_to(target)

    assert read_ledger(tmp_path) == Ledger(exists=True, state=None)


def test_structurally_invalid_state_is_present_but_unreadable(tmp_path: Path) -> None:
    path = tmp_path / ".ebpy" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"version": 1, "rules": {"F401": "broken"}, "counters": {}}',
        encoding="utf-8",
    )

    assert read_ledger(tmp_path) == Ledger(exists=True, state=None)


def test_falsy_containers_with_the_wrong_type_are_not_valid_state() -> None:
    valid = {"version": 1, "rules": {}, "counters": {}, "log": []}

    for field, invalid in (("rules", []), ("counters", []), ("log", {})):
        assert state_from_dict({**valid, field: invalid}) is None


def test_invalid_ceiling_fields_are_not_coerced_into_valid_state() -> None:
    valid = {"version": 1, "rules": {}, "counters": {}, "log": []}

    assert state_from_dict({**valid, "phase": "unknown"}) is None
    assert state_from_dict({**valid, "updatedAt": 42}) is None
    assert state_from_dict({**valid, "frozenAt": ""}) is None
    assert (
        state_from_dict(
            {
                **valid,
                "rules": {"F401": {"baseline": True, "current": 1, "status": "draining"}},
            }
        )
        is None
    )
    assert state_from_dict({**valid, "counters": {"mypy:errors": {"baseline": -1, "current": 1}}}) is None


def test_a_log_cannot_grow_without_bound() -> None:
    state = empty_state()
    for index in range(250):
        state = append_log(state, "note", f"entry {index}", None)
    assert len(state.log) == 200
    assert state.log[-1].text == "entry 249"
