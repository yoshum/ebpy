"""The CI gate: fail when anything rose above its ceiling."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..baseline import cells_for, finding_total, split_against_baseline
from ..ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..measurement import (
    AnalyzerStatus,
    Failed,
    Measured,
    Measurement,
    Observation,
    Unavailable,
    classify,
    measure_repository,
)
from ..models import AnalysisMeasurement, CellCounts, State, ToolingPresence
from ..quality_file import write_quality_file
from ..state import apply_analyzer_rule_counts, copy_state, total_violations, write_state

_WORST_SAMPLE = 5

# Mapped explicitly, not with getattr(tooling, name): the roster of analyzers this ebpy
# ships is fixed and short, and a literal table keeps a typo in a name a mypy error rather
# than a silently-always-false lookup. The noun is what the standing note says is unratcheted.
_CONFIGURED_ANALYZERS: tuple[tuple[str, Callable[[ToolingPresence], bool], str], ...] = (
    ("mypy", lambda tooling: tooling.mypy, "Type errors"),
    ("ruff", lambda tooling: tooling.ruff, "Lint violations"),
)


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class CheckDecision:
    result: CheckResult
    state: State


def _worst(cells: CellCounts) -> list[str]:
    ranked = sorted(
        ((file, rule, count) for file, rules in cells.items() for rule, count in rules.items()),
        key=lambda item: (-item[2], item[0], item[1]),
    )
    return [f"  {file}  {rule}  +{count}" for file, rule, count in ranked[:_WORST_SAMPLE]]


def _excess_reason(excess: CellCounts) -> str:
    return "\n".join(
        [
            f"{finding_total(excess)} finding(s) beyond the ceiling — these are new since the baseline:",
            *_worst(excess),
            "",
            "Fix them, or if a rule was genuinely reconfigured, re-freeze with --force.",
        ]
    )


def _incomplete_reason(analyzer: str, result: AnalysisMeasurement) -> str:
    files = sorted({item.file for item in result.unattributed})
    return "\n".join(
        [
            f"{len(result.unattributed)} syntax error(s) — {analyzer} could not lint {len(files)} file(s):",
            *(f"  {item.file}:{item.line}  {item.message}" for item in result.unattributed[:_WORST_SAMPLE]),
            "A file that does not parse is invisible to every rule, so it cannot pass",
            "by having no count.",
        ]
    )


def _unmeasured_reason(analyzer: str, observation: Unavailable | Failed | None) -> str:
    # `observation` is None only for a contract analyzer this ebpy build has no runner for
    # at all — classify()'s fail-closed case — so there is no tool detail to quote.
    detail = observation.detail if observation is not None else f"{analyzer} has no runner in this ebpy build"
    return "\n".join(
        [
            f"{analyzer} could not be measured, so its ceiling went unverified:",
            *(f"  {line}" for line in detail.splitlines()),
            "A ceiling nobody measured cannot be reported as held.",
        ]
    )


def _unverified_reason(
    analyzer: str, status: AnalyzerStatus, observation: Observation[AnalysisMeasurement] | None
) -> str:
    if status == "incomplete":
        assert isinstance(observation, Measured)
        return _incomplete_reason(analyzer, observation.value)
    # `classify` only returns "unavailable" or "failed" for these two shapes (or None).
    assert observation is None or isinstance(observation, Unavailable | Failed)
    return _unmeasured_reason(analyzer, observation)


def _gate_analyzer(
    state: State, analyzer: str, baseline: CellCounts, measurement: Measurement
) -> tuple[State, str | None]:
    """Apply one analyzer's ratchet, returning the updated state and its failure reason if any.

    An analyzer that could not be measured leaves the state's rules for its namespace
    untouched — a ceiling nobody looked at is neither held nor broken, so nothing about
    it is written this run.
    """
    observation = measurement.analyzers.get(analyzer)
    status = classify(observation)
    if status != "complete":
        return state, _unverified_reason(analyzer, status, observation)
    assert isinstance(observation, Measured)
    excess, held = split_against_baseline(
        cells_for(observation.value.cells, analyzer), cells_for(baseline, analyzer)
    )
    state = apply_analyzer_rule_counts(state, analyzer, held, "observe")
    return state, _excess_reason(excess) if excess else None


def _non_contract_note(analyzer: str, status: AnalyzerStatus) -> str:
    if status == "complete":
        return f"{analyzer} ran but is not in the frozen contract, so its findings are not ratcheted."
    return f"{analyzer} was not measured and has no ceiling here."


def _non_contract_notes(frozen_analyzers: tuple[str, ...], measurement: Measurement) -> list[str]:
    """Every analyzer this run attempted that the contract does not hold, never gated."""
    roster = set(frozen_analyzers)
    return [
        _non_contract_note(analyzer, classify(observation))
        for analyzer, observation in sorted(measurement.analyzers.items())
        if analyzer not in roster
    ]


def _standing_note(analyzer: str, noun: str) -> str:
    return "\n".join(
        [
            f"{analyzer} is configured in this repository but is not in the frozen contract.",
            f"{noun} are not ratcheted. `ebpy freeze --analyzer {analyzer}` puts it under the ceiling.",
        ]
    )


def _standing_notes(previous: State) -> list[str]:
    """Every run, name a configured analyzer the contract omits — whether or not it ran.

    Read from `previous.diagnosis.tooling`, detected from configuration rather than from
    installs, so this survives the tool being absent. Skipped when there is no diagnosis to
    compare against: a repository that never ran `diagnose` has nothing to compare against,
    and inventing a complaint from missing data is exactly what "absence and zero are
    different" forbids.
    """
    if previous.diagnosis is None:
        return []
    tooling = previous.diagnosis.tooling
    roster = set(previous.frozen_analyzers)
    return [
        _standing_note(analyzer, noun)
        for analyzer, configured, noun in _CONFIGURED_ANALYZERS
        if analyzer not in roster and configured(tooling)
    ]


def check_measurement(previous: State, baseline: CellCounts, measurement: Measurement) -> CheckDecision:
    """Apply one repository measurement without reading tools or writing artifacts."""
    state = copy_state(previous)
    failures: list[str] = []
    for analyzer in sorted(previous.frozen_analyzers):
        state, failure = _gate_analyzer(state, analyzer, baseline, measurement)
        if failure is not None:
            failures.append(failure)

    notes = [*_non_contract_notes(previous.frozen_analyzers, measurement), *_standing_notes(previous)]

    if failures:
        return CheckDecision(CheckResult(ok=False, message="\n\n".join([*failures, *notes])), state)

    message = "\n\n".join(
        [
            f"Clean. {total_violations(state)} grandfathered findings left to drain across "
            f"{len(previous.frozen_analyzers)} analyzers.",
            *notes,
        ]
    )
    return CheckDecision(CheckResult(ok=True, message=message), state)


def run_check(cwd: Path, write: bool) -> CheckResult:
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        return CheckResult(ok=False, message=invalid_artifacts_message(artifacts))
    if artifacts.kind == "fresh":
        return CheckResult(ok=False, message="No baseline. Run `ebpy freeze` and commit the result.")
    previous = artifacts.ledger.state
    assert previous is not None

    decision = check_measurement(previous, artifacts.cells, measure_repository(cwd))
    if write:
        write_state(cwd, decision.state)
        write_quality_file(cwd, decision.state)
    return decision.result
