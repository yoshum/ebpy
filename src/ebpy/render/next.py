"""Terminal rendering of the drain plan."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ebpy.decide.drain_order import DrainPlan

_FILES_SHOWN = 10
_RULES_SHOWN = 8
_TAILS_SHOWN = 6

_EMPTY = (
    "Nothing is grandfathered here — either the baseline is not frozen yet (`ebpy freeze`), "
    "or the backlog is empty."
)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _widest(values: list[str]) -> int:
    return max((len(value) for value in values), default=0)


def _overflow(total: int, shown: int) -> list[str]:
    """A section that silently showed its first ten rows would read as "that is all"."""
    return [f"      + {total - shown} more"] if total > shown else []


def _section(title: str, rows: list[str], total: int, shown: int) -> list[str]:
    return [] if not rows else ["", title, *rows, *_overflow(total, shown)]


def _reach(plan: DrainPlan, file: str) -> str:
    """Only when --fan-in gathered it, and only above zero: printing "imported by 0" on
    every row of a repository never asked for the graph reads as a measurement rather
    than as an absence.
    """
    importers = plan.importers.get(file)
    return "" if not importers else f"  (imported by {importers})"


def _take_first_rows(plan: DrainPlan) -> list[str]:
    shown = list(plan.take_first[:_FILES_SHOWN])
    width = _widest([entry.file for entry in shown])
    return [
        f"  {entry.count:>3}  {entry.file:<{width}}  {entry.rule}{_reach(plan, entry.file)}"
        for entry in shown
    ]


def _rule_rows(plan: DrainPlan) -> list[str]:
    shown = list(plan.rules[:_RULES_SHOWN])
    count_width = _widest([str(rule.violations) for rule in shown])
    file_width = _widest([_plural(rule.files, "file") for rule in shown])
    return [
        f"  {rule.violations:>{count_width}} in {_plural(rule.files, 'file'):<{file_width}}   {rule.rule}"
        for rule in shown
    ]


def _tail_rows(plan: DrainPlan) -> list[str]:
    shown = list(plan.directory_tails[:_TAILS_SHOWN])
    width = _widest([tail.directory for tail in shown])
    return [f"  {tail.directory:<{width}}  {tail.rule}  —  {', '.join(tail.files)}" for tail in shown]


def _heavy_rows(plan: DrainPlan) -> list[str]:
    width = _widest([_plural(file.violations, "violation") for file in plan.heaviest])
    return [
        f"  {_plural(file.violations, 'violation'):>{width}} across {_plural(file.rules, 'rule')}"
        f"   {file.file}{_reach(plan, file.file)}"
        for file in plan.heaviest
    ]


def render_next(plan: DrainPlan) -> str:
    """Render the ``ebpy next`` drain guidance for a drain plan."""
    if plan.totals.violations == 0:
        return "\n".join(["ebpy next", "", _EMPTY, ""])
    headline = (
        f"{_plural(plan.totals.violations, 'violation')} · {_plural(plan.totals.files, 'file')}"
        f" · {_plural(plan.totals.rules, 'rule')} still grandfathered"
    )
    return "\n".join(
        [
            "ebpy next",
            "",
            headline,
            *_section(
                "take these first — one or two edits, and the rule is enforced in that file for good:",
                _take_first_rows(plan),
                len(plan.take_first),
                _FILES_SHOWN,
            ),
            *_section(
                "rules by the files you have to touch, not by the violations:",
                _rule_rows(plan),
                len(plan.rules),
                _RULES_SHOWN,
            ),
            *_section(
                "the last files carrying a rule in their directory:",
                _tail_rows(plan),
                len(plan.directory_tails),
                _TAILS_SHOWN,
            ),
            *_section(
                "leave these until last — that count is a redesign, not a backlog:",
                _heavy_rows(plan),
                len(plan.heaviest),
                len(plan.heaviest),
            ),
            "",
        ]
    )
