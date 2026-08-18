"""The CI gate: fail when anything rose above its ceiling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..baseline import read_cells, split_against_baseline
from ..ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..mypy_runner import run_mypy_error_count
from ..quality_file import write_quality_file
from ..ruff_runner import run_ruff_check
from ..state import (
    MYPY_COUNTER,
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


def _worst(counts: dict[str, int]) -> list[str]:
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:_WORST_SAMPLE]
    return [f"  {count}  {rule}" for rule, count in ranked]


def run_check(cwd: Path, write: bool) -> CheckResult:
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        return CheckResult(ok=False, message=invalid_artifacts_message(artifacts))
    if artifacts.kind == "fresh":
        return CheckResult(ok=False, message="No baseline. Run `ebpy freeze` and commit the result.")
    previous = artifacts.ledger.state
    assert previous is not None

    result = run_ruff_check(cwd)
    baseline = read_cells(cwd)
    new_by_rule, grandfathered = split_against_baseline(result.cells, baseline)

    state = apply_rule_counts(previous, grandfathered, "observe")
    mypy_errors = run_mypy_error_count(cwd)
    if mypy_errors is not None:
        state = set_counter(state, MYPY_COUNTER, mypy_errors, "observe")
    if write:
        write_state(cwd, state)
        write_quality_file(cwd, state)

    if result.unattributed:
        files = sorted({item.file for item in result.unattributed})
        return CheckResult(
            ok=False,
            message="\n".join(
                [
                    f"{len(result.unattributed)} syntax error(s) — Ruff could not lint {len(files)} file(s):",
                    *(
                        f"  {item.file}:{item.line}  {item.message}"
                        for item in result.unattributed[:_WORST_SAMPLE]
                    ),
                    "A file that does not parse is invisible to every rule, so it cannot pass",
                    "by having no count.",
                ]
            ),
        )

    new_total = sum(new_by_rule.values())
    if new_total > 0:
        return CheckResult(
            ok=False,
            message="\n".join(
                [
                    f"{new_total} violation(s) beyond the ceiling — these are new since the baseline:",
                    *_worst(new_by_rule),
                    "",
                    "Fix them, or if a rule was genuinely reconfigured, re-freeze with --force.",
                ]
            ),
        )

    regressions = find_regressions(state)
    if regressions:
        return CheckResult(
            ok=False,
            message="\n".join(
                [
                    "Counts grew past their ceiling:",
                    *(
                        f"  {item.name}: {item.baseline} -> {item.current} (+{item.current - item.baseline})"
                        for item in regressions
                    ),
                ]
            ),
        )

    return CheckResult(
        ok=True,
        message=f"Clean. {total_violations(state)} grandfathered violations left to drain.",
    )
