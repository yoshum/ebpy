"""The backlog as a rule x area matrix, so the shape of the debt is visible.

Where ``next`` answers "which edit enforces the most", this answers "what does
this repository's lint debt actually look like".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import CellCountsView

# A file at the repository root belongs to no directory, and "" reads as missing data.
ROOT_AREA = "(root)"

Matrix = dict[str, dict[str, int]]


def area_of(file: str) -> str:
    first, _, rest = file.partition("/")
    return ROOT_AREA if not rest or not first else first


@dataclass(frozen=True)
class ReportRow:
    rule: str
    total: int
    # Counts in the same order as the section's areas, so the renderer does no lookups.
    counts: tuple[int, ...]


@dataclass(frozen=True)
class ReportSection:
    title: str
    total: int
    areas: tuple[str, ...]
    rows: tuple[ReportRow, ...]


@dataclass(frozen=True)
class LintReport:
    new_total: int
    backlog_total: int
    mypy_errors: int | None
    files_with_findings: int
    # Rule totals only: after a freeze a violation beyond the ceiling is new, and the
    # check output already named where.
    new_rules: tuple[tuple[str, int], ...]
    sections: tuple[ReportSection, ...]
    # Why no lint ran, when none did — the report then covers the ratchet file and
    # nothing else, and a reader has to be able to tell "no debt" from "nobody looked".
    lint_failure: str | None
    # Why no type check ran, when none did — same distinction, second capability: the
    # counter reads "not measured" and this says which tool could not say otherwise.
    mypy_failure: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "newTotal": self.new_total,
            "backlogTotal": self.backlog_total,
            "mypyErrors": self.mypy_errors,
            "filesWithFindings": self.files_with_findings,
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
            "lintFailure": self.lint_failure,
            "mypyFailure": self.mypy_failure,
        }


def matrix_from_cells(cells: CellCountsView) -> Matrix:
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


@dataclass(frozen=True)
class Unmeasured:
    """Why each capability could not be measured, for the ones that could not.

    One value rather than a reason per parameter: capabilities are added over time, and a
    builder that grows an argument for each is how a report ends up with five booleans.
    """

    lint: str | None = None
    mypy: str | None = None


def build_lint_report(
    new_by_rule: dict[str, int] | None,
    backlog_matrix: Matrix,
    mypy_errors: int | None,
    files_with_findings: int,
    unmeasured: Unmeasured,
) -> LintReport:
    new_rules = tuple(sorted((new_by_rule or {}).items(), key=lambda item: (-item[1], item[0])))
    return LintReport(
        new_total=sum(count for _, count in new_rules),
        backlog_total=_matrix_total(backlog_matrix),
        mypy_errors=mypy_errors,
        files_with_findings=files_with_findings,
        new_rules=new_rules,
        sections=tuple(_section_of("Backlog — grandfathered, drains rule by rule", backlog_matrix)),
        lint_failure=unmeasured.lint,
        mypy_failure=unmeasured.mypy,
    )
