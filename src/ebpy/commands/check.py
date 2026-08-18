"""The CI gate: fail when anything rose above its ceiling."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from ..baseline import split_against_baseline
from ..ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..measurement import Measured, Measurement, measure_repository
from ..models import MYPY_COUNTER, CellCounts, State
from ..quality_file import write_quality_file
from ..state import (
    apply_rule_counts,
    find_regressions,
    set_counter,
    total_violations,
    write_state,
)

_WORST_SAMPLE = 5


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class CheckDecision:
    result: CheckResult
    state: State | None


def _worst(counts: dict[str, int]) -> list[str]:
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:_WORST_SAMPLE]
    return [f"  {count}  {rule}" for rule, count in ranked]


def check_measurement(previous: State, baseline: CellCounts, measurement: Measurement) -> CheckDecision:
    """Apply one repository measurement without reading tools or writing artifacts."""
    lint = measurement.lint
    if not isinstance(lint, Measured):
        return CheckDecision(CheckResult(ok=False, message=lint.detail), state=None)

    result = lint.value
    new_by_rule, grandfathered = split_against_baseline(result.cells, baseline)

    state = apply_rule_counts(deepcopy(previous), grandfathered, "observe")
    mypy = measurement.counters[MYPY_COUNTER]
    if isinstance(mypy, Measured):
        state = set_counter(state, MYPY_COUNTER, mypy.value, "observe")

    if result.unattributed:
        files = sorted({item.file for item in result.unattributed})
        return CheckDecision(
            CheckResult(
                ok=False,
                message="\n".join(
                    [
                        f"{len(result.unattributed)} syntax error(s) — "
                        f"Ruff could not lint {len(files)} file(s):",
                        *(
                            f"  {item.file}:{item.line}  {item.message}"
                            for item in result.unattributed[:_WORST_SAMPLE]
                        ),
                        "A file that does not parse is invisible to every rule, so it cannot pass",
                        "by having no count.",
                    ]
                ),
            ),
            state,
        )

    new_total = sum(new_by_rule.values())
    if new_total > 0:
        return CheckDecision(
            CheckResult(
                ok=False,
                message="\n".join(
                    [
                        f"{new_total} violation(s) beyond the ceiling — these are new since the baseline:",
                        *_worst(new_by_rule),
                        "",
                        "Fix them, or if a rule was genuinely reconfigured, re-freeze with --force.",
                    ]
                ),
            ),
            state,
        )

    regressions = find_regressions(state)
    if regressions:
        return CheckDecision(
            CheckResult(
                ok=False,
                message="\n".join(
                    [
                        "Counts grew past their ceiling:",
                        *(
                            f"  {item.name}: {item.baseline} -> {item.current} "
                            f"(+{item.current - item.baseline})"
                            for item in regressions
                        ),
                    ]
                ),
            ),
            state,
        )

    return CheckDecision(
        CheckResult(
            ok=True,
            message=f"Clean. {total_violations(state)} grandfathered violations left to drain.",
        ),
        state,
    )


def run_check(cwd: Path, write: bool) -> CheckResult:
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        return CheckResult(ok=False, message=invalid_artifacts_message(artifacts))
    if artifacts.kind == "fresh":
        return CheckResult(ok=False, message="No baseline. Run `ebpy freeze` and commit the result.")
    previous = artifacts.ledger.state
    assert previous is not None

    decision = check_measurement(previous, artifacts.cells, measure_repository(cwd))
    if write and decision.state is not None:
        write_state(cwd, decision.state)
        write_quality_file(cwd, decision.state)
    return decision.result
