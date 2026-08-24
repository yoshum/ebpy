"""The drain order, computed rather than guessed.

The baseline records a count per file per rule, and the ratchet works the same
way — a file with no cell left for a rule fails on the next violation of it,
whatever that rule's total is elsewhere. So the useful question is not "which
rule is smallest" but "which edit enforces the most".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import Suppression

# A file within this many violations of clean for one rule is one edit, not a project.
CHEAP_VIOLATION_LIMIT = 2

# A rule surviving in this few files of a directory is that directory's last holdout.
DIRECTORY_TAIL_LIMIT = 2

HEAVY_FILES_SHOWN = 5


@dataclass(frozen=True)
class Totals:
    """The backlog counted three ways: total violations, distinct files, and distinct rules."""

    violations: int
    files: int
    rules: int


@dataclass(frozen=True)
class RuleSpread:
    """One rule's spread: how many violations it has and across how many files."""

    rule: str
    violations: int
    files: int


@dataclass(frozen=True)
class DirectoryTail:
    """The last files carrying a rule in a directory, with the rule and its remaining violations."""

    directory: str
    rule: str
    files: tuple[str, ...]
    violations: int


@dataclass(frozen=True)
class HeavyFile:
    """A file heavy enough to leave for last: how many rules it carries and how many violations."""

    file: str
    rules: int
    violations: int


@dataclass(frozen=True)
class DrainPlan:
    """The computed drain order: totals, take-first cells, rule spreads, directory tails and heavy files."""

    totals: Totals
    take_first: tuple[Suppression, ...]
    rules: tuple[RuleSpread, ...]
    directory_tails: tuple[DirectoryTail, ...]
    heaviest: tuple[HeavyFile, ...]
    # Files in the backlog to how many files import them. Empty unless --fan-in asked.
    importers: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the drain plan to a JSON-ready dict with camelCase keys."""
        return {
            "totals": {
                "violations": self.totals.violations,
                "files": self.totals.files,
                "rules": self.totals.rules,
            },
            "takeFirst": [{"file": s.file, "rule": s.rule, "count": s.count} for s in self.take_first],
            "rules": [{"rule": r.rule, "violations": r.violations, "files": r.files} for r in self.rules],
            "directoryTails": [
                {"directory": t.directory, "rule": t.rule, "files": list(t.files), "violations": t.violations}
                for t in self.directory_tails
            ],
            "heaviest": [
                {"file": h.file, "rules": h.rules, "violations": h.violations} for h in self.heaviest
            ],
            "importers": dict(self.importers),
        }


def totals_of(entries: list[Suppression]) -> Totals:
    return Totals(
        violations=sum(entry.count for entry in entries),
        files=len({entry.file for entry in entries}),
        rules=len({entry.rule for entry in entries}),
    )


def cheapest_first(entries: list[Suppression], limit: int = CHEAP_VIOLATION_LIMIT) -> list[Suppression]:
    """The cheapest cells are not merely small — each one converts a file from
    grandfathered to enforced, permanently, for the cost of one or two edits.
    """
    cheap = [entry for entry in entries if entry.count <= limit]
    return sorted(cheap, key=lambda entry: (entry.count, entry.file, entry.rule))


def rule_spread(entries: list[Suppression]) -> list[RuleSpread]:
    """Ranked by files to touch rather than by violations. Forty violations in three
    files and forty across thirty are the same number in `status` and ten times apart
    in work.
    """
    groups: dict[str, list[Suppression]] = {}
    for entry in entries:
        groups.setdefault(entry.rule, []).append(entry)
    spread = [
        RuleSpread(rule=rule, violations=sum(e.count for e in group), files=len(group))
        for rule, group in groups.items()
    ]
    return sorted(spread, key=lambda item: (item.files, item.violations, item.rule))


def _directory_of(file: str) -> str:
    parent = str(PurePosixPath(file).parent)
    return "(root)" if parent == "." else parent


def directory_tails(entries: list[Suppression], limit: int = DIRECTORY_TAIL_LIMIT) -> list[DirectoryTail]:
    """Directories where a rule survives in a handful of files. This says what it
    measures — the last files *carrying* the rule — and not that the rest of the
    directory is clean: a file Ruff never looks at has no cell either, and no
    arithmetic over this file can tell the two apart.
    """
    groups: dict[tuple[str, str], list[Suppression]] = {}
    for entry in entries:
        groups.setdefault((_directory_of(entry.file), entry.rule), []).append(entry)
    tails = [
        DirectoryTail(
            directory=directory,
            rule=rule,
            files=tuple(sorted(e.file for e in group)),
            violations=sum(e.count for e in group),
        )
        for (directory, rule), group in groups.items()
        if len(group) <= limit
    ]
    return sorted(tails, key=lambda tail: (len(tail.files), tail.violations, tail.directory, tail.rule))


def heaviest_files(entries: list[Suppression], limit: int = HEAVY_FILES_SHOWN) -> list[HeavyFile]:
    """Heavy means ONE rule the file cannot clear in a couple of edits, not a large
    total: a file holding two rules at one violation each sums past any cheap threshold
    while every cell in it is a quick win. A file with one cheap rule and one enormous
    one belongs in both lists, and that is the useful answer — take the quick win,
    leave the rest.
    """
    groups: dict[str, list[Suppression]] = {}
    for entry in entries:
        groups.setdefault(entry.file, []).append(entry)
    heavy = [
        HeavyFile(file=file, rules=len(group), violations=sum(e.count for e in group))
        for file, group in groups.items()
        if any(e.count > CHEAP_VIOLATION_LIMIT for e in group)
    ]
    return sorted(heavy, key=lambda item: (-item.violations, -item.rules, item.file))[:limit]


def build_drain_plan(entries: list[Suppression], importers: dict[str, int] | None = None) -> DrainPlan:
    return DrainPlan(
        totals=totals_of(entries),
        take_first=tuple(cheapest_first(entries)),
        rules=tuple(rule_spread(entries)),
        directory_tails=tuple(directory_tails(entries)),
        heaviest=tuple(heaviest_files(entries)),
        importers=importers or {},
    )
