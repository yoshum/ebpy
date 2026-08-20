"""P2: pin today's violations as the ceiling.

Running a global freeze a second time is refused: that would grandfather everything added
since, which is the one thing the baseline exists to prevent. Use --force or --analyzer
to recover from that state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..errors import CommandError
from ..measurement import (
    ANALYZER_NAMES,
    AnalyzerStatus,
    Failed,
    Measured,
    Measurement,
    Unavailable,
    classify,
    measure_repository,
)
from ..models import AnalysisMeasurement, CellCounts, CellCountsView, State
from ..quality_file import write_quality_file
from ..store.baseline import (
    cells_excluding,
    cells_for,
    finding_total,
    merge_cells,
    rule_totals,
    write_cells,
)
from ..store.ceiling_artifacts import CeilingArtifacts, invalid_artifacts_message, read_ceiling_artifacts
from ..store.state import (
    copy_state,
    empty_state,
    replace_analyzer_rules,
    with_phase,
    write_state,
)

_UNATTRIBUTED_SHOWN = 5


@dataclass(frozen=True)
class FreezeDecision:
    cells: CellCountsView
    state: State
    message: str


def _unattributed_report(analyzer: str, result: AnalysisMeasurement) -> list[str]:
    """Syntax errors are not rule violations the baseline can grandfather: a file that
    does not parse is invisible to every rule, so recording a count for it would be a
    lie. Naming the files turns a mystery into a task."""
    if not result.unattributed:
        return []
    files = sorted({item.file for item in result.unattributed})
    samples = [
        f"  {item.file}:{item.line}  {item.message}" for item in result.unattributed[:_UNATTRIBUTED_SHOWN]
    ]
    more = len(result.unattributed) - len(samples)
    return [
        "",
        f"WARNING: {len(result.unattributed)} syntax error(s) in {len(files)} file(s) — "
        f"{analyzer} could not lint them:",
        *samples,
        *([f"  + {more} more"] if more > 0 else []),
        "These cannot be grandfathered: a file that does not parse has no violations to count.",
        f"Fix them, or exclude them in {analyzer}'s configuration if deliberately unparseable.",
        "Then re-run freeze so those files enter the baseline.",
    ]


def _already_frozen(artifacts: CeilingArtifacts) -> str:
    state = artifacts.ledger.state
    assert state is not None and state.frozen_at is not None
    return "\n".join(
        [
            f"Already frozen at {state.frozen_at}.",
            "Freezing again would grandfather everything added since, which is the one thing the",
            "baseline exists to prevent. To reclaim cells you have fixed, run `ebpy prune`.",
            "To deliberately replace the contract, re-run with --force.",
        ]
    )


def _previous_state(artifacts: CeilingArtifacts, force: bool) -> State:
    """Choose metadata to preserve; a forced recovery trusts no invalid artifact."""
    if artifacts.kind == "invalid":
        return empty_state()
    # Copied because the branch below rewrites it: `artifacts` is the ledger as read from
    # disk, and a caller that re-reads it must not find the fields --force cleared.
    state = copy_state(artifacts.ledger.state) if artifacts.ledger.state else empty_state()
    if force:
        # `--force` pins a complete new contract. Keeping old rules from an unmeasured
        # contract would make the result depend on the contract it claims to replace.
        # The roster is kept: a forced freeze must still cover every analyzer the old
        # contract named, or it would drop one it has no runner for rather than refuse.
        state.rules = {}
    return state


def _refusal_reason(
    analyzer: str,
    status: AnalyzerStatus,
    observation: Measured[AnalysisMeasurement] | Unavailable | Failed | None,
) -> str:
    """One paragraph per analyzer that cannot be included in the contract.

    The route offered differs: install the tool, fix the file, or investigate a failure.
    All three are actionable; none offer a way to freeze around the missing data, because a
    contract that silently omits an analyzer is indistinguishable from one that measured zero.
    """
    if status == "no-runner":
        # A contract analyzer this build has no runner for at all, so there is no tool
        # detail to quote — classify() reports "no-runner" precisely to word this apart.
        return "\n".join(
            [
                f"{analyzer} is in the contract but this ebpy build has no runner for it.",
                "Freeze with a build that can measure it, or the ceiling it holds cannot be re-pinned.",
            ]
        )
    if status == "unavailable":
        return "\n".join(
            [
                f"{analyzer} is not installed. Install it first: `ebpy bootstrap` is the step.",
                "Do not freeze without it — a ceiling that omits an analyzer cannot be trusted.",
            ]
        )
    if status == "failed":
        assert isinstance(observation, Failed)
        return "\n".join(
            [
                f"{analyzer} ran but could not produce a measurement:",
                *(f"  {line}" for line in observation.detail.splitlines()),
                "Fix the configuration error and re-run.",
            ]
        )
    # "incomplete": syntax errors block attribution.
    assert isinstance(observation, Measured)
    result = observation.value
    files = sorted({item.file for item in result.unattributed})
    samples = [
        f"  {item.file}:{item.line}  {item.message}" for item in result.unattributed[:_UNATTRIBUTED_SHOWN]
    ]
    more = len(result.unattributed) - len(samples)
    return "\n".join(
        [
            f"{analyzer} found {len(result.unattributed)} syntax error(s) in {len(files)} file(s) "
            "that it could not lint:",
            *samples,
            *([f"  + {more} more"] if more > 0 else []),
            f"Fix the files, or exclude them in {analyzer}'s configuration if deliberately unparseable.",
        ]
    )


def _check_scope_preconditions(artifacts: CeilingArtifacts, scope: str, force: bool) -> str | None:
    """Return an error message if the artifact precondition for a scoped freeze is not met."""
    if artifacts.kind != "frozen":
        return "\n".join(
            [
                f"Cannot add {scope} to an unfrozen pair.",
                "`ebpy freeze --analyzer` requires a valid frozen contract to extend.",
                "Run `ebpy freeze` first to establish the initial contract.",
            ]
        )
    assert artifacts.ledger.state is not None
    roster = artifacts.ledger.state.frozen_analyzers
    if not force and scope in roster:
        return "\n".join(
            [
                f"{scope} is already in the frozen contract.",
                f"Use `ebpy freeze --force --analyzer {scope}` to re-pin it.",
            ]
        )
    return None


def _build_global_freeze(
    previous: State,
    measurement: Measurement,
    force: bool,
    frozen_at: str,
) -> FreezeDecision:
    """Merge every in-scope analyzer's cells into one contract, requiring all to be complete.

    The scope is every analyzer this build ships plus every analyzer the contract being
    replaced already froze. A rostered analyzer this build has no runner for cannot be
    measured, so it fails the freeze closed rather than being silently dropped — no
    invocation, `--force` included, removes an analyzer from a contract.
    """
    scope = sorted(set(ANALYZER_NAMES) | set(previous.frozen_analyzers))
    observations = {a: measurement.analyzers.get(a) for a in scope}
    incomplete: list[str] = []
    for analyzer in scope:
        obs = observations[analyzer]
        status = classify(obs)
        if status != "complete":
            incomplete.append(_refusal_reason(analyzer, status, obs))
    if incomplete:
        raise CommandError("\n\n".join([*incomplete, "", "Nothing was written."]))

    parts: list[CellCounts] = []
    unattributed_reports: list[str] = []
    for analyzer in scope:
        obs = observations[analyzer]
        assert isinstance(obs, Measured)
        parts.append(cells_for(obs.value.cells, analyzer))
        unattributed_reports.extend(_unattributed_report(analyzer, obs.value))

    cells = merge_cells(parts)
    state = copy_state(previous)
    for analyzer in scope:
        obs = observations[analyzer]
        assert isinstance(obs, Measured)
        state = replace_analyzer_rules(state, analyzer, rule_totals(cells_for(cells, analyzer)))
    state.frozen_analyzers = tuple(scope)
    state.frozen_at = frozen_at
    state = with_phase(state, "drain")

    backlog = finding_total(cells)
    rule_count = len(rule_totals(cells))
    verb = "Re-pinned" if force else "Baseline pinned"
    message = "\n".join(
        [
            f"{verb}: {backlog} violations across {rule_count} rules are now grandfathered.",
            "New code is held to the full rule set from here.",
            *unattributed_reports,
            "",
            "Commit .ebpy/baseline.json, .ebpy/state.json and QUALITY.md.",
            "Next: `ebpy next` ranks what to drain first.",
        ]
    )
    return FreezeDecision(cells, state, message)


def _build_scoped_freeze(
    previous: State,
    baseline: CellCountsView,
    measurement: Measurement,
    scope: str,
) -> FreezeDecision:
    """Add or replace one analyzer's namespace without touching any other.

    The global frozen_at is preserved: a scoped write shows up in updated_at, not frozen_at.
    """
    obs = measurement.analyzers.get(scope)
    status = classify(obs)
    if status != "complete":
        raise CommandError("\n\n".join([_refusal_reason(scope, status, obs), "", "Nothing was written."]))

    assert isinstance(obs, Measured)
    scope_cells = cells_for(obs.value.cells, scope)
    # Strip this namespace from the baseline; merge_cells will catch any accidental overlap.
    other_cells = cells_excluding(baseline, scope)

    cells = merge_cells([other_cells, scope_cells])

    state = copy_state(previous)
    state = replace_analyzer_rules(state, scope, rule_totals(scope_cells))
    if scope not in state.frozen_analyzers:
        state.frozen_analyzers = tuple(sorted((*state.frozen_analyzers, scope)))

    unattributed = _unattributed_report(scope, obs.value)
    backlog = finding_total(scope_cells)
    rule_count = len(rule_totals(scope_cells))
    message = "\n".join(
        [
            f"{scope}: {backlog} violations across {rule_count} rules added to the ceiling.",
            "All other analyzer namespaces are untouched.",
            *unattributed,
            "",
            "Commit .ebpy/baseline.json, .ebpy/state.json and QUALITY.md.",
        ]
    )
    return FreezeDecision(cells, state, message)


def freeze_measurement(
    previous: State,
    baseline: CellCountsView,
    measurement: Measurement,
    scope: str | None,
    force: bool,
    frozen_at: str,
) -> FreezeDecision:
    """Build a ceiling contract from one measurement without writing it.

    `scope` is the --analyzer NAME value (None = global). `baseline` is the existing frozen cells;
    a global or force freeze may start from an empty baseline. `force` is passed to the global
    path to distinguish an initial freeze from a re-pin in the output message.
    """
    if scope is None:
        return _build_global_freeze(previous, measurement, force, frozen_at)
    return _build_scoped_freeze(previous, baseline, measurement, scope)


def run_freeze(cwd: Path, force: bool, analyzer: str | None) -> str:
    artifacts = read_ceiling_artifacts(cwd)

    if analyzer is not None:
        # Scoped freeze: artifact precondition is a valid frozen pair.
        precondition_error = _check_scope_preconditions(artifacts, analyzer, force)
        if precondition_error is not None:
            raise CommandError(precondition_error)
    elif not force:
        # Global freeze: read before measuring so a repository that must not be frozen
        # cannot have its ceiling raised by the run that discovers it.
        if artifacts.kind == "invalid":
            raise CommandError(invalid_artifacts_message(artifacts))
        if artifacts.kind == "frozen":
            raise CommandError(_already_frozen(artifacts))

    previous = _previous_state(artifacts, force and analyzer is None)
    frozen_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    decision = freeze_measurement(
        previous,
        artifacts.cells,
        measure_repository(cwd),
        analyzer,
        force,
        frozen_at,
    )
    write_cells(cwd, decision.cells)
    write_state(cwd, decision.state)
    write_quality_file(cwd, decision.state)
    return decision.message
