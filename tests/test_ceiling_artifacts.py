from __future__ import annotations

import json
from pathlib import Path

from ebpy.cell_key import analyzer_of
from ebpy.models import RuleBaseline
from ebpy.store.baseline import write_cells
from ebpy.store.ceiling_artifacts import read_ceiling_artifacts
from ebpy.store.state import empty_state, state_path, write_state


def frozen_state(
    cwd: Path, rules: dict[str, int] | None = None, analyzers: tuple[str, ...] | None = None
) -> None:
    rules = rules or {}
    roster = analyzers if analyzers is not None else tuple(sorted({analyzer_of(rule) for rule in rules}))
    state = empty_state()
    state.rules = {
        name: RuleBaseline(baseline=count, current=count, status="enforced" if count == 0 else "draining")
        for name, count in rules.items()
    }
    state.frozen_analyzers = roster
    state.frozen_at = "2026-08-19T00:00:00Z"
    state.phase = "drain"
    write_state(cwd, state)


def test_no_artifacts_is_a_fresh_repository(tmp_path: Path) -> None:
    assert read_ceiling_artifacts(tmp_path).kind == "fresh"


def test_a_valid_pre_freeze_ledger_is_still_fresh(tmp_path: Path) -> None:
    write_state(tmp_path, empty_state())

    assert read_ceiling_artifacts(tmp_path).kind == "fresh"


def test_a_matching_baseline_and_frozen_ledger_is_frozen(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"ruff:F401": 2}})
    frozen_state(tmp_path, {"ruff:F401": 2})

    assert read_ceiling_artifacts(tmp_path).kind == "frozen"


def test_a_clean_frozen_repository_is_distinct_from_a_fresh_one(tmp_path: Path) -> None:
    write_cells(tmp_path, {})
    frozen_state(tmp_path, analyzers=("ruff",))

    assert read_ceiling_artifacts(tmp_path).kind == "frozen"


def test_a_baseline_without_its_ledger_is_invalid(tmp_path: Path) -> None:
    write_cells(tmp_path, {})

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_a_frozen_ledger_without_its_baseline_is_invalid(tmp_path: Path) -> None:
    frozen_state(tmp_path)

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_a_pre_freeze_ledger_with_a_recorded_roster_is_invalid(tmp_path: Path) -> None:
    """A ledger's roster is ceiling data: carrying one before `frozen_at` is set means the
    ledger claims an analyzer was frozen while no freeze happened, which the missing
    baseline.json cannot possibly back up."""
    state = empty_state()
    state.frozen_analyzers = ("mypy",)
    write_state(tmp_path, state)

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_a_baseline_with_a_pre_freeze_ledger_is_invalid(tmp_path: Path) -> None:
    write_cells(tmp_path, {})
    write_state(tmp_path, empty_state())

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_disagreeing_rule_ceilings_are_invalid(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"ruff:F401": 2}})
    frozen_state(tmp_path, {"ruff:F401": 1})

    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "invalid"
    assert artifacts.detail is not None and "disagree" in artifacts.detail


def test_a_baseline_namespace_missing_from_the_roster_is_invalid(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"mypy:arg-type": 3}})
    frozen_state(tmp_path, analyzers=("ruff",))

    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "invalid"
    assert artifacts.detail is not None and "analyzer" in artifacts.detail


def test_a_frozen_ledger_with_an_empty_roster_is_invalid(tmp_path: Path) -> None:
    write_cells(tmp_path, {})
    frozen_state(tmp_path, analyzers=())

    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "invalid"
    assert artifacts.detail is not None and "no analyzers" in artifacts.detail


def test_a_ledger_with_rules_but_no_frozen_at_is_invalid_not_fresh(tmp_path: Path) -> None:
    """A ledger holding ceiling rules but missing `frozenAt` records no valid freeze, so it
    is neither fresh (a fresh state has no rules) nor a usable contract — it is invalid."""
    state_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    state_path(tmp_path).write_text(
        json.dumps(
            {
                "version": 2,
                "tool": "ebpy",
                "phase": "drain",
                "updatedAt": "2026-08-19T00:00:00Z",
                "frozenAt": None,
                "frozenAnalyzers": ["ruff"],
                "rules": {"ruff:F401": {"baseline": 2, "current": 2, "status": "draining"}},
                "log": [],
            }
        ),
        encoding="utf-8",
    )

    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "invalid"
    assert artifacts.detail is not None and "contains ceiling data" in artifacts.detail
