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
    AnalyzerStatus,
    Failed,
    Measured,
    Measurement,
    Unavailable,
    classify,
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
from ..store.ceiling_artifacts import (
    CeilingArtifacts,
    align_all_analyzer_rules_to_cells,
    align_analyzer_rules_to_cells,
    invalid_artifacts_message,
    read_ceiling_artifacts,
)
from ..store.config import read_config
from ..store.state import (
    copy_state,
    empty_state,
    with_phase,
    write_state,
)
from ..tools import ANALYZER_NAMES, measure_repository

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
                "Resolve the failure above and re-run.",
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
    """Return an error message if the artifact precondition for a scoped freeze is not met.

    A fresh pair is allowed: `freeze --analyzer NAME` on a repository with no contract yet
    builds a narrow contract holding only NAME, the staged-adoption path for a repository
    whose toolchain is not yet complete. An invalid pair is still refused — a partial contract
    cannot be read and preserved, so recovering it needs a global `freeze --force`.
    """
    if artifacts.kind == "invalid":
        return "\n".join(
            [
                f"Cannot add {scope} to an invalid contract.",
                "`ebpy freeze --analyzer` requires a valid pair it can read and preserve.",
                "Recover with `ebpy freeze --force`, which discards the old contract entirely.",
            ]
        )
    state = artifacts.ledger.state
    roster = state.frozen_analyzers if state is not None else ()
    if not force and scope in roster:
        return "\n".join(
            [
                f"{scope} is already in the frozen contract.",
                f"Use `ebpy freeze --force --analyzer {scope}` to re-pin it.",
            ]
        )
    return None


def build_global_freeze(
    previous: State,
    measurement: Measurement,
    force: bool,
    frozen_at: str,
    scope: list[str],
) -> FreezeDecision:
    """Merge every in-scope analyzer's cells into one contract, requiring all to be complete.

    ``scope`` is the sorted analyzer set to pin; it is supplied by the caller so that
    config-declared sets and the default union (all registered names plus previously
    frozen names) can both drive this function without the function knowing the source.
    ``frozen_analyzers`` is set to exactly ``scope``, so dropping an analyzer from the
    contract requires the caller to narrow the scope — which means declaring fewer analyzers
    in ``.ebpy/config.json`` and running with ``--force``, since a non-force re-freeze is
    refused. Within that scope the function fails closed: any analyzer it cannot completely
    measure prevents the freeze rather than being silently omitted.
    """
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
    state = align_all_analyzer_rules_to_cells(copy_state(previous), cells, scope)
    state.frozen_analyzers = tuple(scope)
    state.frozen_at = frozen_at
    state = with_phase(state, "drain")

    backlog = finding_total(cells)
    rule_count = len(rule_totals(cells))
    analyzer_count = len(scope)
    verb = "Re-pinned" if force else "Baseline pinned"
    message = "\n".join(
        [
            f"{verb}: {backlog} violations across {rule_count} rules "
            f"and {analyzer_count} analyzers are now grandfathered.",
            "New code is held to the full rule set from here.",
            *unattributed_reports,
            "",
            "Commit .ebpy/baseline.json, .ebpy/state.json and QUALITY.md.",
            "Next: `ebpy next` ranks what to drain first.",
        ]
    )
    return FreezeDecision(cells, state, message)


def build_scoped_freeze(
    previous: State,
    baseline: CellCountsView,
    measurement: Measurement,
    scope: str,
    frozen_at: str,
) -> FreezeDecision:
    """Add or replace one analyzer's namespace without touching any other.

    On an already-frozen contract the global frozen_at is preserved — a scoped write shows up
    in updated_at, not frozen_at. On a fresh pair this is the initial freeze, so it stamps
    frozen_at and advances to the drain phase, building a narrow contract holding only `scope`.
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

    replacing = scope in previous.frozen_analyzers
    state = align_analyzer_rules_to_cells(copy_state(previous), scope_cells, scope)
    if not replacing:
        state.frozen_analyzers = tuple(sorted((*state.frozen_analyzers, scope)))
    if state.frozen_at is None:
        state.frozen_at = frozen_at
        state = with_phase(state, "drain")

    unattributed = _unattributed_report(scope, obs.value)
    backlog = finding_total(scope_cells)
    rule_count = len(rule_totals(scope_cells))
    headline = (
        f"{scope}: ceiling replaced with {backlog} violations across {rule_count} rules."
        if replacing
        else f"{scope}: {backlog} violations across {rule_count} rules added to the ceiling."
    )
    message = "\n".join(
        [
            headline,
            "All other analyzer namespaces are untouched.",
            *unattributed,
            "",
            "Commit .ebpy/baseline.json, .ebpy/state.json and QUALITY.md.",
        ]
    )
    return FreezeDecision(cells, state, message)


def run_freeze(cwd: Path, force: bool, analyzer: str | None) -> str:
    config = read_config(cwd)
    artifacts = read_ceiling_artifacts(cwd)

    if analyzer is not None:
        # Scoped freeze: artifact precondition is a fresh or a valid frozen pair.
        precondition_error = _check_scope_preconditions(artifacts, analyzer, force)
        if precondition_error is not None:
            raise CommandError(precondition_error)
        # When a config is present, only declared analyzers may be targeted.
        if config is not None and analyzer not in config.analyzers:
            declared = ", ".join(config.analyzers)
            raise CommandError(
                f"{analyzer} is not in the declared analyzer set in .ebpy/config.json ({declared})."
            )
    elif not force:
        # Global freeze: read before measuring so a repository that must not be frozen
        # cannot have its ceiling raised by the run that discovers it.
        if artifacts.kind == "invalid":
            raise CommandError(invalid_artifacts_message(artifacts))
        if artifacts.kind == "frozen":
            raise CommandError(_already_frozen(artifacts))

    previous = _previous_state(artifacts, force and analyzer is None)
    frozen_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    measurement = measure_repository(cwd)
    if analyzer is None:
        if config is not None:
            scope = sorted(config.analyzers)
        else:
            scope = sorted(set(ANALYZER_NAMES) | set(previous.frozen_analyzers))
        decision = build_global_freeze(previous, measurement, force, frozen_at, scope)
    else:
        decision = build_scoped_freeze(previous, artifacts.cells, measurement, analyzer, frozen_at)
    write_cells(cwd, decision.cells)
    write_state(cwd, decision.state)
    write_quality_file(cwd, decision.state)
    return decision.message
