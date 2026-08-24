"""The CI gate: fail when anything rose above its ceiling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..measurement import (
    AnalyzerStatus,
    Failed,
    Measured,
    Measurement,
    Observation,
    Unavailable,
    classify,
)
from ..models import AnalysisMeasurement, CellCounts, State
from ..quality_file import write_quality_file
from ..store.baseline import cells_for, finding_total, split_against_baseline
from ..store.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts, reconcile_scope
from ..store.config import read_config
from ..store.state import apply_analyzer_rule_counts, copy_state, total_violations, write_state
from ..tools import ANALYZERS_BY_NAME, measure_repository

_WORST_SAMPLE = 5


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


def _excess_reason(analyzer: str, excess: CellCounts) -> str:
    return "\n".join(
        [
            f"{finding_total(excess)} finding(s) beyond the ceiling — these are new since the baseline:",
            *_worst(excess),
            "",
            f"Fix them, or if a {analyzer} rule was genuinely reconfigured, re-pin only that",
            f"namespace with `ebpy freeze --force --analyzer {analyzer}`.",
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
    # at all — classify()'s "no-runner" case — so there is no tool detail to quote.
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
    # `classify` only returns "unavailable", "failed", or "no-runner" here; the first two
    # carry an observation to quote, "no-runner" carries None.
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
    return state, _excess_reason(analyzer, excess) if excess else None


def _non_contract_note(analyzer: str, status: AnalyzerStatus) -> str:
    """One paragraph for a non-contract analyzer this run attempted.

    check speaks only about what it measured: an analyzer that ran has unratcheted findings,
    one that could not run has no verifiable ceiling here. The standing "configured but not
    ratcheted" advice — which needs no measurement to state — lives in the diagnosis gap
    instead, so it is not restated from here.
    """
    if status == "complete":
        lines = [f"{analyzer} ran but is not in the frozen contract, so its findings are not ratcheted."]
        # Only a registered analyzer can be frozen, so only it earns the freeze hint.
        if analyzer in ANALYZERS_BY_NAME:
            lines.append(f"`ebpy freeze --analyzer {analyzer}` puts it under the ceiling.")
        return "\n".join(lines)
    return f"{analyzer} was not measured and has no ceiling here."


def _non_contract_notes(previous: State, measurement: Measurement) -> list[str]:
    """One note per analyzer this run attempted outside the frozen contract, sorted by name.

    Derived from the measurement alone: a note is a report of what ran, never a complaint
    reconstructed from the diagnosis.
    """
    roster = set(previous.frozen_analyzers)
    return [
        _non_contract_note(analyzer, classify(observation))
        for analyzer, observation in sorted(measurement.analyzers.items())
        if analyzer not in roster
    ]


def check_measurement(previous: State, baseline: CellCounts, measurement: Measurement) -> CheckDecision:
    """Apply one repository measurement without reading tools or writing artifacts."""
    state = copy_state(previous)
    failures: list[str] = []
    for analyzer in sorted(previous.frozen_analyzers):
        state, failure = _gate_analyzer(state, analyzer, baseline, measurement)
        if failure is not None:
            failures.append(failure)

    notes = _non_contract_notes(previous, measurement)

    if failures:
        return CheckDecision(CheckResult(ok=False, message="\n\n".join([*failures, *notes])), state)

    count = len(previous.frozen_analyzers)
    message = "\n\n".join(
        [
            f"Clean. {total_violations(state)} grandfathered findings left to drain across "
            f"{count} {'analyzer' if count == 1 else 'analyzers'}.",
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

    mismatch = reconcile_scope(read_config(cwd), previous)
    if mismatch is not None:
        return CheckResult(ok=False, message=mismatch)

    decision = check_measurement(previous, artifacts.cells, measure_repository(cwd))
    if write:
        write_state(cwd, decision.state)
        write_quality_file(cwd, decision.state)
    return decision.result
