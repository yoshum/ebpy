"""What `prune` does with a per-analyzer namespaced ceiling, and what it refuses.

`prune` is documented as safe to run at any point, because it can only ever lower a
cell. That claim holds only for cells clamped by the baseline file, so a prune without
a ledger to name the frozen contract would pin today's counts instead — hence the
refusals below. When it does run, each analyzer is treated on its own: a complete
measurement lowers that namespace's ceiling, while an analyzer that could not be
measured carries its ceiling through untouched rather than losing it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.baseline import BASELINE_FILE, baseline_path, write_cells
from ebpy.ceiling_artifacts import read_ceiling_artifacts
from ebpy.commands.prune import prune_measurement, run_prune
from ebpy.errors import CommandError
from ebpy.measurement import Failed, Measured, Measurement, Unavailable
from ebpy.models import AnalysisMeasurement, CellCounts, RuleBaseline, State, UnattributedFinding
from ebpy.state import empty_state, state_path, write_state


def _state(frozen_analyzers: tuple[str, ...], rules: dict[str, RuleBaseline]) -> State:
    return State(frozen_analyzers=frozen_analyzers, rules=rules)


def _frozen(baseline: int) -> RuleBaseline:
    return RuleBaseline(baseline=baseline, current=baseline, status="draining")


def _measured(analyzer: str, cells: CellCounts) -> Measured[AnalysisMeasurement]:
    return Measured(tool=analyzer, value=AnalysisMeasurement(cells=cells))


def _incomplete(analyzer: str) -> Measured[AnalysisMeasurement]:
    """A run that left an unattributed finding, so classify() calls it "incomplete"."""
    return Measured(
        tool=analyzer,
        value=AnalysisMeasurement(
            cells={},
            unattributed=(UnattributedFinding(file="src/broken.py", line=1, message="syntax error"),),
        ),
    )


def test_prune_refuses_when_the_ledger_is_missing(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/app.py": {"ruff:F401": 1}})
    before = (tmp_path / BASELINE_FILE).read_text(encoding="utf-8")

    with pytest.raises(CommandError, match=r"state\.json"):
        run_prune(tmp_path)

    assert (tmp_path / BASELINE_FILE).read_text(encoding="utf-8") == before
    assert not state_path(tmp_path).exists()


def test_prune_before_the_first_freeze_writes_nothing(tmp_path: Path) -> None:
    """`diagnose --write` and `log` both create a valid ledger before freeze. Its mere
    existence must not let prune create `{}`, which freeze would mistake for a ceiling
    pinned on a clean tree."""
    write_state(tmp_path, empty_state())
    state_before = state_path(tmp_path).read_text(encoding="utf-8")

    with pytest.raises(CommandError, match="freeze"):
        run_prune(tmp_path)

    assert not baseline_path(tmp_path).exists()
    assert state_path(tmp_path).read_text(encoding="utf-8") == state_before


def test_prune_lowers_a_complete_analyzer_and_preserves_a_failed_ones_cells() -> None:
    """A complete analyzer's namespace is pruned to what still exists; a failed one's
    baseline cells are carried through unchanged, since a ceiling nobody re-measured
    cannot be lowered."""
    previous = _state(("mypy", "ruff"), {"ruff:F401": _frozen(2), "mypy:arg-type": _frozen(3)})
    baseline: CellCounts = {"src/a.py": {"ruff:F401": 2}, "src/b.py": {"mypy:arg-type": 3}}
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {"src/a.py": {"ruff:F401": 1}}),
            "mypy": Failed(tool="mypy", failure_kind="execution-failed", detail="mypy blew up"),
        }
    )

    decision = prune_measurement(previous, baseline, measurement)

    assert decision.cells == {"src/a.py": {"ruff:F401": 1}, "src/b.py": {"mypy:arg-type": 3}}
    assert decision.state.rules["ruff:F401"].baseline == 1
    assert decision.state.rules["mypy:arg-type"].baseline == 3


def test_prune_preserves_a_failed_analyzers_state_rules() -> None:
    """The state rules of an analyzer that could not be measured are left exactly as they
    were — not drained, not re-frozen — because this run learned nothing about them."""
    previous = _state(
        ("mypy", "ruff"),
        {"ruff:F401": _frozen(2), "mypy:arg-type": RuleBaseline(baseline=3, current=3, status="draining")},
    )
    baseline: CellCounts = {"src/a.py": {"ruff:F401": 2}, "src/b.py": {"mypy:arg-type": 3}}
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {"src/a.py": {"ruff:F401": 1}}),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    decision = prune_measurement(previous, baseline, measurement)

    assert decision.state.rules["mypy:arg-type"] == RuleBaseline(baseline=3, current=3, status="draining")
    assert decision.state.rules["ruff:F401"].baseline == 1


def test_prune_reports_reclaimed_totals_per_analyzer() -> None:
    """The message names the total reclaimed and breaks it down by analyzer, so a reader
    can see which ceiling came down."""
    previous = _state(("mypy", "ruff"), {"ruff:F401": _frozen(4), "mypy:arg-type": _frozen(3)})
    baseline: CellCounts = {"src/a.py": {"ruff:F401": 4}, "src/b.py": {"mypy:arg-type": 3}}
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {"src/a.py": {"ruff:F401": 1}}),
            "mypy": _measured("mypy", {"src/b.py": {"mypy:arg-type": 2}}),
        }
    )

    decision = prune_measurement(previous, baseline, measurement)

    assert "Reclaimed 4 violations" in decision.message
    assert "ruff" in decision.message
    assert "mypy" in decision.message
    assert "-3" in decision.message  # the ruff namespace fell from 4 to 1
    assert "-1" in decision.message  # the mypy namespace fell from 3 to 2
    assert "Commit .ebpy/baseline.json together with the fix" in decision.message


def test_prune_with_no_complete_analyzer_changes_nothing_and_says_why() -> None:
    """With not a single analyzer measured, prune is a no-op: both artifacts are left as
    they were and the message explains why, rather than raising."""
    previous = _state(("mypy", "ruff"), {"ruff:F401": _frozen(2), "mypy:arg-type": _frozen(3)})
    baseline: CellCounts = {"src/a.py": {"ruff:F401": 2}, "src/b.py": {"mypy:arg-type": 3}}
    measurement = Measurement(
        analyzers={
            "ruff": Failed(tool="ruff", failure_kind="execution-failed", detail="ruff failed"),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    decision = prune_measurement(previous, baseline, measurement)

    assert decision.cells == baseline
    assert decision.state.rules == previous.rules
    assert "ruff failed" in decision.message
    assert "mypy is not installed" in decision.message


def test_prune_never_raises_a_cell() -> None:
    """A cell where the current count exceeds the baseline is clamped to the baseline —
    prune only ever lowers a ceiling, never raises it."""
    previous = _state(("ruff",), {"ruff:F401": _frozen(2)})
    baseline: CellCounts = {"src/a.py": {"ruff:F401": 2}}
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {"src/a.py": {"ruff:F401": 9}})})

    decision = prune_measurement(previous, baseline, measurement)

    assert decision.cells == {"src/a.py": {"ruff:F401": 2}}
    assert decision.state.rules["ruff:F401"].baseline == 2


def test_prune_of_a_fully_fixed_rule_drops_it_from_both_artifacts() -> None:
    """A rule whose every finding is fixed leaves the namespace entirely: it is dropped
    from the cells written to baseline.json and from the ledger's rules. Holding a
    positive baseline for a rule the baseline file no longer carries would make the two
    artifacts disagree, and the next command would read the pair as invalid."""
    previous = _state(("ruff",), {"ruff:F401": _frozen(3), "ruff:E501": _frozen(2)})
    baseline: CellCounts = {"src/a.py": {"ruff:F401": 3}, "src/b.py": {"ruff:E501": 2}}
    # F401 is entirely fixed; only E501 still has a finding.
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {"src/b.py": {"ruff:E501": 1}})})

    decision = prune_measurement(previous, baseline, measurement)

    assert "ruff:F401" not in decision.state.rules
    assert not any("ruff:F401" in rules for rules in decision.cells.values())
    assert decision.state.rules["ruff:E501"].baseline == 1


def test_prune_of_a_fully_fixed_rule_keeps_the_pair_readable(tmp_path: Path) -> None:
    """After draining a rule to zero, the written baseline.json and state.json still agree,
    so the next command classifies the contract as frozen rather than invalid."""
    write_cells(tmp_path, {"src/a.py": {"ruff:F401": 3}})
    write_state(
        tmp_path,
        State(
            version=2,
            phase="drain",
            frozen_at="2026-01-01T00:00:00Z",
            frozen_analyzers=("ruff",),
            rules={"ruff:F401": _frozen(3)},
        ),
    )
    previous = read_ceiling_artifacts(tmp_path)
    assert previous.kind == "frozen"
    assert previous.ledger.state is not None

    # No finding survives: prune must lower the ceiling to nothing.
    decision = prune_measurement(
        previous.ledger.state,
        previous.cells,
        Measurement(analyzers={"ruff": _measured("ruff", {})}),
    )
    write_cells(tmp_path, decision.cells)
    write_state(tmp_path, decision.state)

    assert read_ceiling_artifacts(tmp_path).kind == "frozen"


def test_prune_measurement_does_not_mutate_its_input_state() -> None:
    """`prune_measurement` is pure over its arguments: the caller's `previous` state must
    be untouched even as the returned decision carries a lowered ceiling."""
    previous = _state(("ruff",), {"ruff:F401": _frozen(2)})
    baseline: CellCounts = {"src/a.py": {"ruff:F401": 2}}
    measurement = Measurement(analyzers={"ruff": _measured("ruff", {"src/a.py": {"ruff:F401": 1}})})

    decision = prune_measurement(previous, baseline, measurement)

    assert previous.rules["ruff:F401"].baseline == 2
    assert decision.state.rules["ruff:F401"].baseline == 1


def test_prune_records_no_ceiling_for_an_unmeasured_analyzer_with_no_prior_ceiling() -> None:
    """An analyzer in the contract that this run could not measure and that has no baseline
    cell records nothing — absence stays absence rather than becoming a zero ceiling."""
    previous = _state(("mypy", "ruff"), {"ruff:F401": _frozen(2)})
    baseline: CellCounts = {"src/a.py": {"ruff:F401": 2}}
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {"src/a.py": {"ruff:F401": 1}}),
            "mypy": Unavailable(tool="mypy", detail="mypy is not installed"),
        }
    )

    decision = prune_measurement(previous, baseline, measurement)

    assert "mypy:arg-type" not in decision.state.rules
    assert not any("mypy:" in rule for rules in decision.cells.values() for rule in rules)
    assert "mypy is not installed" in decision.message


def test_prune_carries_an_incomplete_analyzer_through_unchanged() -> None:
    """An analyzer whose run left an unattributed finding is not "complete", so its ceiling
    is carried through rather than lowered from a partial measurement."""
    previous = _state(("mypy", "ruff"), {"ruff:F401": _frozen(2), "mypy:arg-type": _frozen(3)})
    baseline: CellCounts = {"src/a.py": {"ruff:F401": 2}, "src/b.py": {"mypy:arg-type": 3}}
    measurement = Measurement(
        analyzers={
            "ruff": _measured("ruff", {"src/a.py": {"ruff:F401": 1}}),
            "mypy": _incomplete("mypy"),
        }
    )

    decision = prune_measurement(previous, baseline, measurement)

    assert decision.cells["src/b.py"] == {"mypy:arg-type": 3}
    assert decision.state.rules["mypy:arg-type"].baseline == 3
    assert decision.state.rules["ruff:F401"].baseline == 1
