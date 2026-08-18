from __future__ import annotations

from pathlib import Path

from ebpy.baseline import write_cells
from ebpy.ceiling_artifacts import read_ceiling_artifacts
from ebpy.models import Counter
from ebpy.state import apply_rule_counts, empty_state, write_state


def frozen_state(cwd: Path, rules: dict[str, int] | None = None) -> None:
    state = apply_rule_counts(empty_state(), rules or {}, "freeze")
    state.frozen_at = "2026-08-19T00:00:00Z"
    state.phase = "drain"
    write_state(cwd, state)


def test_no_artifacts_is_a_fresh_repository(tmp_path: Path) -> None:
    assert read_ceiling_artifacts(tmp_path).kind == "fresh"


def test_a_valid_pre_freeze_ledger_is_still_fresh(tmp_path: Path) -> None:
    write_state(tmp_path, empty_state())

    assert read_ceiling_artifacts(tmp_path).kind == "fresh"


def test_a_matching_baseline_and_frozen_ledger_is_frozen(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"F401": 2}})
    frozen_state(tmp_path, {"F401": 2})

    assert read_ceiling_artifacts(tmp_path).kind == "frozen"


def test_a_clean_frozen_repository_is_distinct_from_a_fresh_one(tmp_path: Path) -> None:
    write_cells(tmp_path, {})
    frozen_state(tmp_path)

    assert read_ceiling_artifacts(tmp_path).kind == "frozen"


def test_a_baseline_without_its_ledger_is_invalid(tmp_path: Path) -> None:
    write_cells(tmp_path, {})

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_a_frozen_ledger_without_its_baseline_is_invalid(tmp_path: Path) -> None:
    frozen_state(tmp_path)

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_ceiling_counts_without_a_freeze_are_invalid(tmp_path: Path) -> None:
    state = empty_state()
    state.counters = {"mypy:errors": Counter(baseline=1, current=1)}
    write_state(tmp_path, state)

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_a_baseline_with_a_pre_freeze_ledger_is_invalid(tmp_path: Path) -> None:
    write_cells(tmp_path, {})
    write_state(tmp_path, empty_state())

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_disagreeing_rule_ceilings_are_invalid(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"F401": 2}})
    frozen_state(tmp_path, {"F401": 1})

    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "invalid"
    assert artifacts.detail is not None and "disagree" in artifacts.detail
