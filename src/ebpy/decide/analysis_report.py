"""The backlog as a rule x area matrix, so the shape of the debt is visible.

Where ``next`` answers "which edit enforces the most", this answers "what does
this repository's lint debt actually look like".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from ebpy.measurement import AnalyzerStatus, Measured, Measurement, classify
from ebpy.store.baseline import (
    cells_for,
    finding_total,
    merge_cells,
    prune_cells,
    rule_totals,
    split_against_baseline,
)

if TYPE_CHECKING:
    from ebpy.models import CellCounts, CellCountsView, UnattributedFinding

# report's own widening of the seam's vocabulary. `AnalyzerStatus` itself is not widened:
# check, freeze and prune reconcile before measuring, so they never reach this state, and a
# value unreachable in the seam is a value every caller has to handle for nothing.
ReportAnalyzerStatus = AnalyzerStatus | Literal["scope-mismatch"]

# A file at the repository root belongs to no directory, and "" reads as missing data.
ROOT_AREA = "(root)"

Matrix = dict[str, dict[str, int]]

# Maximum unattributed samples to include in the report — the same cap the CLI uses for
# its worst-cell sample so the two outputs carry proportionate detail.
_WORST_SAMPLE = 5


def area_of(file: str) -> str:
    """Return the top-level area a file belongs to — its first path segment, or the root marker."""
    first, _, rest = file.partition("/")
    return ROOT_AREA if not rest or not first else first


@dataclass(frozen=True)
class ReportRow:
    """One rule's row in a section: the rule, its total, and its per-area counts in the section's order."""

    rule: str
    total: int
    # Counts in the same order as the section's areas, so the renderer does no lookups.
    counts: tuple[int, ...]


@dataclass(frozen=True)
class ReportSection:
    """A group of rules under a shared title, the areas they span, and the rows that fill the matrix."""

    title: str
    total: int
    areas: tuple[str, ...]
    rows: tuple[ReportRow, ...]


@dataclass(frozen=True)
class AnalyzerSummary:
    """One analyzer's state in the report: its findings, files, and any failure or unattributed detail."""

    in_contract: bool
    status: ReportAnalyzerStatus
    # Attributed cell total for a Measured observation; None when unavailable or failed.
    findings: int | None
    files_with_findings: int | None
    # The observation's detail for unavailable and failed observations; None otherwise.
    failure: str | None
    unattributed_total: int
    unattributed: tuple[UnattributedFinding, ...]


@dataclass(frozen=True)
class AnalysisReport:
    """The backlog as a rule-by-area matrix: new totals, sections, and each analyzer's summary."""

    new_total: int
    backlog_total: int
    # Rule totals only: the report answers "what does this debt look like",
    # and `check` is where a reader is sent for the individual cells.
    new_rules: tuple[tuple[str, int], ...]
    sections: tuple[ReportSection, ...]
    # Sorted by analyzer name, so the output is deterministic.
    analyzers: tuple[tuple[str, AnalyzerSummary], ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a JSON-ready dict with camelCase keys."""
        return {
            "newTotal": self.new_total,
            "backlogTotal": self.backlog_total,
            "newRules": [{"rule": rule, "count": count} for rule, count in self.new_rules],
            "sections": [
                {
                    "title": section.title,
                    "total": section.total,
                    "areas": list(section.areas),
                    "rows": [
                        {"rule": row.rule, "total": row.total, "counts": list(row.counts)}
                        for row in section.rows
                    ],
                }
                for section in self.sections
            ],
            "analyzers": {
                name: {
                    "inContract": summary.in_contract,
                    "status": summary.status,
                    "findings": summary.findings,
                    "filesWithFindings": summary.files_with_findings,
                    "failure": summary.failure,
                    "unattributedTotal": summary.unattributed_total,
                    "unattributed": [
                        {"file": u.file, "line": u.line, "message": u.message} for u in summary.unattributed
                    ],
                }
                for name, summary in self.analyzers
            },
        }


def matrix_from_cells(cells: CellCountsView) -> Matrix:
    """Fold cells into a rule-by-area matrix, summing each rule's counts within an area."""
    matrix: Matrix = {}
    for file, rules in cells.items():
        area = matrix.setdefault(area_of(file), {})
        for rule, count in rules.items():
            area[rule] = area.get(rule, 0) + count
    return matrix


def _matrix_total(matrix: Matrix) -> int:
    return sum(sum(rules.values()) for rules in matrix.values())


def _section_of(title: str, matrix: Matrix) -> list[ReportSection]:
    total = _matrix_total(matrix)
    if total == 0:
        return []
    areas = tuple(
        area for area, _ in sorted(matrix.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    )
    rules = sorted({rule for area_rules in matrix.values() for rule in area_rules})
    rows = tuple(
        sorted(
            (
                ReportRow(
                    rule=rule,
                    total=sum(matrix[area].get(rule, 0) for area in areas),
                    counts=tuple(matrix[area].get(rule, 0) for area in areas),
                )
                for rule in rules
            ),
            key=lambda row: (-row.total, row.rule),
        )
    )
    return [ReportSection(title=title, total=total, areas=areas, rows=rows)]


def _analyzer_summary(
    analyzer: str, in_contract: bool, measurement: Measurement, mismatched: bool
) -> AnalyzerSummary:
    observation = measurement.analyzers.get(analyzer)
    status: ReportAnalyzerStatus = "scope-mismatch" if mismatched else classify(observation)
    if not isinstance(observation, Measured):
        detail = observation.detail if observation is not None else None
        return AnalyzerSummary(
            in_contract=in_contract,
            status=status,
            findings=None,
            files_with_findings=None,
            failure=detail,
            unattributed_total=0,
            unattributed=(),
        )
    value = observation.value
    unattributed_total = len(value.unattributed)
    unattributed = value.unattributed[:_WORST_SAMPLE] if unattributed_total else ()
    return AnalyzerSummary(
        in_contract=in_contract,
        status=status,
        findings=finding_total(cells_for(value.cells, analyzer)),
        files_with_findings=value.files_with_findings,
        failure=None,
        unattributed_total=unattributed_total,
        unattributed=unattributed,
    )


def _backlog_cells_for(analyzer: str, baseline: CellCounts, measurement: Measurement) -> CellCounts:
    """Backlog cells for one contract analyzer.

    A complete observation is pruned to only what still exists; anything else falls
    back to the analyzer's baseline unchanged, and the caller flags the fallback via
    the analyzer's status.
    """
    observation = measurement.analyzers.get(analyzer)
    if isinstance(observation, Measured) and classify(observation) == "complete":
        return prune_cells(cells_for(baseline, analyzer), cells_for(observation.value.cells, analyzer))
    return cells_for(baseline, analyzer)


def report_from_measurement(
    baseline: CellCounts,
    frozen_analyzers: tuple[str, ...],
    measurement: Measurement,
    scope_mismatches: frozenset[str] = frozenset(),
) -> AnalysisReport:
    """Build a report from facts; tool failure changes its detail, never its exit status.

    `scope_mismatches` is computed by `ScopeDecision`, which is the only value that knows all
    three authorities. Deriving it here from `frozen - measurement.analyzers` would miss the
    config-declared-but-unfrozen direction entirely, since a declared analyzer is always
    measured.
    """
    contract_set = set(frozen_analyzers)
    all_analyzers = sorted(set(measurement.analyzers) | contract_set)

    analyzer_summaries = tuple(
        (a, _analyzer_summary(a, a in contract_set, measurement, a in scope_mismatches))
        for a in all_analyzers
    )

    # Accumulate new violations and backlog from every contract analyzer.
    complete_excess_parts: list[CellCounts] = []
    backlog_parts: list[CellCounts] = []
    for analyzer in sorted(frozen_analyzers):
        observation = measurement.analyzers.get(analyzer)
        status = classify(observation)
        backlog_parts.append(_backlog_cells_for(analyzer, baseline, measurement))
        if status == "complete":
            assert isinstance(observation, Measured)
            excess, _ = split_against_baseline(
                cells_for(observation.value.cells, analyzer),
                cells_for(baseline, analyzer),
            )
            complete_excess_parts.append(excess)

    merged_excess = merge_cells(complete_excess_parts)
    merged_backlog = merge_cells(backlog_parts)
    backlog_matrix = matrix_from_cells(merged_backlog)

    new_by_rule = rule_totals(merged_excess)
    new_rules = tuple(sorted(new_by_rule.items(), key=lambda item: (-item[1], item[0])))

    return AnalysisReport(
        new_total=sum(count for _, count in new_rules),
        backlog_total=_matrix_total(backlog_matrix),
        new_rules=new_rules,
        sections=tuple(_section_of("Backlog — grandfathered, drains rule by rule", backlog_matrix)),
        analyzers=analyzer_summaries,
    )
