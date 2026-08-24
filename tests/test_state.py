"""The state ledger: the ratchet invariants, and every way a v2 state reads or is rejected."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ebpy.models import (
    CiCoverage,
    Diagnosis,
    RuleBaseline,
    SizeDistribution,
    State,
    ToolSetup,
    diagnosis_from_dict,
)
from ebpy.store.state import (
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
from ebpy.tools.mypy import MypySetup


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


def test_a_version_one_state_reads_as_unreadable() -> None:
    """Version 1 is no longer upgraded in memory; a state still at version 1 is refused so
    the reader never reconstructs a contract from a format it no longer understands.
    """
    raw = _v1_raw(rules={"F401": {"baseline": 2, "current": 1, "status": "draining"}})

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

    ledger = read_ledger(tmp_path)
    assert ledger.exists is True
    assert ledger.state is None


def test_a_version_one_ledger_is_tagged_as_a_retired_format(tmp_path: Path) -> None:
    """A state.json that parses as JSON and names version 1 is recorded as a retired format, not
    just an unreadable blob — the tag is what lets a command tell "old ebpy wrote this" apart from
    "these bytes are corrupt".
    """
    path = tmp_path / ".ebpy" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "rules": {}, "counters": {}, "log": []}), encoding="utf-8")

    assert read_ledger(tmp_path).legacy_version == 1


def test_a_corrupt_state_carries_no_retired_format_tag(tmp_path: Path) -> None:
    """Bytes that never parse as JSON cannot name a version, so the retired-format tag stays None:
    corruption and an old format must not be conflated.
    """
    path = tmp_path / ".ebpy" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")

    assert read_ledger(tmp_path).legacy_version is None


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


def test_diagnosis_round_trips_tool_setups_without_a_version_bump() -> None:
    """The decomposed diagnosis survives to_dict/from_dict unchanged, under state version 2.

    The state validator only checks that `diagnosis` is a dict, so the diagnosis's internal
    shape — per-detector tool setups plus the residual signals — may change without a bump.
    """
    ci = CiCoverage(
        present=False,
        runners=(),
        unpinned_actions=(),
        runs_lint=False,
        runs_typecheck=False,
        runs_test=False,
        runs_ebpy_check=False,
    )
    diagnosis = Diagnosis(
        package_manager="uv",
        requires_python=">=3.12",
        framework="none",
        tool_setups={
            "ruff": ToolSetup(configured=True),
            "mypy": MypySetup(configured=True, strict=False),
            "secret-scan": ToolSetup(configured=True),
        },
        pre_commit=True,
        agent_instructions=("CLAUDE.md",),
        ci=ci,
        sizes=SizeDistribution(total=0, over_file_limit=0, largest=()),
        gaps=(),
    )

    restored = diagnosis_from_dict(diagnosis.to_dict())

    # Every setup reads back as a base ToolSetup. mypy's strictness is provenance regenerated on
    # the next diagnose, so it is written but never reconstructed — the read-back is not a MypySetup.
    assert restored.tool_setups["mypy"] == ToolSetup(configured=True)
    assert not isinstance(restored.tool_setups["mypy"], MypySetup)
    assert restored.tool_setups["ruff"] == ToolSetup(configured=True)
    assert restored.pre_commit is True
    assert restored.agent_instructions == ("CLAUDE.md",)
    # secret-scan is just another tool setup; the base layer does not special-case it.
    assert restored.tool_setups["secret-scan"] == ToolSetup(configured=True)


def test_a_mypy_setup_serializes_its_strictness() -> None:
    """MypySetup writes `strict` into its dict even when off, so the stored diagnosis records it."""
    assert MypySetup(configured=True, strict=False).to_dict() == {"configured": True, "strict": False}
    assert MypySetup(configured=True, strict=True).to_dict() == {"configured": True, "strict": True}


def test_a_legacy_tooling_diagnosis_is_tolerated_by_ignoring_it() -> None:
    """A diagnosis persisted in the pre-decomposition `tooling` shape must not crash the reader.

    The provenance is regenerated on the next `diagnose`, so the old object is simply ignored.
    """
    legacy: dict[str, Any] = {
        "packageManager": "uv",
        "requiresPython": None,
        "framework": "none",
        "tooling": {"ruff": True, "mypy": True, "secretScanning": True},
        "ci": {},
        "sizes": {},
        "gaps": [],
    }

    restored = diagnosis_from_dict(legacy)

    assert restored.tool_setups == {}


def test_a_log_cannot_grow_without_bound() -> None:
    state = empty_state()
    for index in range(250):
        state = append_log(state, "note", f"entry {index}", None)
    assert len(state.log) == 200
    assert state.log[-1].text == "entry 249"
