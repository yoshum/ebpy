"""Classifying the baseline/state pair, and reconciling the configured analyzers against the roster."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ebpy.cell_key import analyzer_of
from ebpy.models import RuleBaseline, State
from ebpy.store.baseline import write_cells
from ebpy.store.ceiling_artifacts import (
    align_all_analyzer_rules_to_cells,
    align_analyzer_rules_to_cells,
    read_ceiling_artifacts,
    reconcile_scope,
)
from ebpy.store.config import EbpyConfig
from ebpy.store.state import empty_state, state_path, write_state

if TYPE_CHECKING:
    from pathlib import Path


def _state(*analyzers: str) -> State:
    s = empty_state()
    s.frozen_analyzers = tuple(analyzers)
    return s


def test_absent_config_skips_reconciliation() -> None:
    """No config means no reconciliation gate; existing behavior is preserved."""
    assert reconcile_scope(None, _state("ruff")) is None


def test_matching_sets_reconcile() -> None:
    """Declared and frozen analyzer sets that are equal produce no error."""
    assert reconcile_scope(EbpyConfig(("mypy", "ruff")), _state("ruff", "mypy")) is None


def test_declared_but_unfrozen_analyzer_is_flagged() -> None:
    """An analyzer in config but absent from the frozen roster surfaces in the error message."""
    msg = reconcile_scope(EbpyConfig(("ruff", "mypy")), _state("ruff"))
    assert msg is not None
    assert "mypy" in msg
    assert "freeze --analyzer" in msg


def test_frozen_but_undeclared_analyzer_is_flagged() -> None:
    """An analyzer in the frozen roster but absent from config surfaces in the error message."""
    msg = reconcile_scope(EbpyConfig(("ruff",)), _state("ruff", "mypy"))
    assert msg is not None
    assert "mypy" in msg
    assert "--force" in msg


def test_config_adding_and_dropping_simultaneously_reports_both_directions() -> None:
    """When config both adds an analyzer and drops another, both directions appear in the message."""
    # Frozen roster: {ruff, mypy}; config declares {ruff, vulture}.
    msg = reconcile_scope(EbpyConfig(("ruff", "vulture")), _state("ruff", "mypy"))
    assert msg is not None
    # vulture is declared but not yet frozen — needs freeze --analyzer
    assert "vulture" in msg
    assert "freeze --analyzer" in msg
    # mypy is frozen but not declared — needs --force to drop
    assert "mypy" in msg
    assert "--force" in msg


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
    """A pre-freeze ledger carrying a recorded roster is invalid.

    A ledger's roster is ceiling data: carrying one before `frozen_at` is set means the
    ledger claims an analyzer was frozen while no freeze happened, which the missing
    baseline.json cannot possibly back up.
    """
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
    assert artifacts.detail is not None
    assert "disagree" in artifacts.detail


def test_a_baseline_namespace_missing_from_the_roster_is_invalid(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"mypy:arg-type": 3}})
    frozen_state(tmp_path, analyzers=("ruff",))

    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "invalid"
    assert artifacts.detail is not None
    assert "analyzer" in artifacts.detail


def test_a_frozen_ledger_with_an_empty_roster_is_invalid(tmp_path: Path) -> None:
    write_cells(tmp_path, {})
    frozen_state(tmp_path, analyzers=())

    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "invalid"
    assert artifacts.detail is not None
    assert "no analyzers" in artifacts.detail


def test_aligning_a_written_pair_reads_back_as_frozen(tmp_path: Path) -> None:
    """Aligning a written pair reads back as frozen.

    The write-side counterpart to `_validate_frozen_pair`: deriving the ledger totals with
    the helper and writing them alongside the same cells must leave a pair that reads as
    frozen, never invalid — the read-side check the helper exists to satisfy.
    """
    cells = {"src/app.py": {"ruff:F401": 2}, "src/lib.py": {"mypy:arg-type": 3}}
    state = empty_state()
    state.frozen_analyzers = ("mypy", "ruff")
    state.frozen_at = "2026-08-19T00:00:00Z"
    state.phase = "drain"
    state = align_all_analyzer_rules_to_cells(state, cells, ("ruff", "mypy"))
    write_cells(tmp_path, cells)
    write_state(tmp_path, state)

    assert read_ceiling_artifacts(tmp_path).kind == "frozen"


def test_aligning_drops_a_rule_whose_cells_are_gone() -> None:
    """Aligning drops a rule whose cells are gone.

    A rule the fresh cells no longer carry must leave the ledger namespace, not linger at a
    stale baseline — otherwise the pair the read side sees would disagree and read as invalid.
    """
    state = empty_state()
    state.rules = {
        "ruff:F401": RuleBaseline(baseline=2, current=2, status="draining"),
        "ruff:E501": RuleBaseline(baseline=1, current=1, status="draining"),
    }

    aligned = align_analyzer_rules_to_cells(state, {"src/app.py": {"ruff:F401": 2}}, "ruff")

    assert set(aligned.rules) == {"ruff:F401"}
    assert aligned.rules["ruff:F401"].baseline == 2


def test_aligning_one_analyzer_leaves_other_namespaces_untouched() -> None:
    """Aligning one analyzer leaves other namespaces untouched.

    Scoped alignment must rewrite only its own analyzer's rules, mirroring the scoped
    freeze that writes one namespace while preserving every other.
    """
    state = empty_state()
    state.rules = {"mypy:arg-type": RuleBaseline(baseline=3, current=3, status="draining")}

    aligned = align_analyzer_rules_to_cells(state, {"src/app.py": {"ruff:F401": 2}}, "ruff")

    assert aligned.rules["mypy:arg-type"].baseline == 3
    assert aligned.rules["ruff:F401"].baseline == 2


def test_a_ledger_with_rules_but_no_frozen_at_is_invalid_not_fresh(tmp_path: Path) -> None:
    """A ledger with rules but no frozenAt is invalid, not fresh.

    A ledger holding ceiling rules but missing `frozenAt` records no valid freeze, so it
    is neither fresh (a fresh state has no rules) nor a usable contract — it is invalid.
    """
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
    assert artifacts.detail is not None
    assert "contains ceiling data" in artifacts.detail
