"""The ratchet file: ``.ebpy/baseline.json``.

ESLint ships bulk suppressions; Ruff does not, so ebpy carries the equivalent itself, keyed
`{file: {analyzer:rule: {count}}}` inside a versioned wrapper. `freeze` writes it, `check`
compares against it, and `prune` is the only way it falls. Its size is bounded by rules x
files, so reading it whole is safe in a way reading a log never is.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..cell_key import analyzer_of, is_rule_id, normalize_analyzer_path

if TYPE_CHECKING:
    from ..models import CellCounts, CellCountsView, RuleId

BASELINE_FILE = ".ebpy/baseline.json"
BASELINE_VERSION = 2


def baseline_path(cwd: Path) -> Path:
    return cwd / BASELINE_FILE


def _valid_count(entry: object) -> int | None:
    """A cell's stored count: a plain positive int, nothing else. `bool` is a subtype of
    `int` in Python, so `type(count) is not int` is required — `isinstance` would let
    `true` silently through as `1`."""
    if not isinstance(entry, dict) or set(entry) != {"count"}:
        return None
    count = entry["count"]
    if type(count) is not int or count <= 0:
        return None
    return count


def _parse_file_rules(rules: object) -> dict[RuleId, int] | None:
    """One file's rule map, rejecting any key that is not already a namespaced rule ID."""
    if not isinstance(rules, dict) or not rules:
        return None
    parsed: dict[RuleId, int] = {}
    for rule, entry in rules.items():
        if not is_rule_id(rule):
            return None
        count = _valid_count(entry)
        if count is None:
            return None
        parsed[rule] = count
    return parsed


def _parse_files(raw_cells: object, cwd: Path) -> CellCounts | None:
    if not isinstance(raw_cells, dict):
        return None
    cells: CellCounts = {}
    for file, rules in raw_cells.items():
        if not isinstance(file, str) or not file:
            return None
        parsed_rules = _parse_file_rules(rules)
        if parsed_rules is None:
            return None
        normalised = normalize_analyzer_path(file, cwd)
        if normalised in cells:
            return None
        cells[normalised] = parsed_rules
    return cells


def parse_cells(raw: Any, cwd: Path) -> CellCounts | None:
    """Parse the complete baseline, rejecting rather than skipping any bad cell.

    Only ``{"version": 2, "cells": {...}}`` is accepted, and any other top-level key makes
    the whole artifact unreadable rather than silently ignored.
    """
    if not isinstance(raw, dict):
        return None
    if set(raw) != {"version", "cells"} or raw["version"] != BASELINE_VERSION:
        return None
    return _parse_files(raw["cells"], cwd)


@dataclass(frozen=True)
class Ceiling:
    """What ``.ebpy/baseline.json`` says about a ceiling having been pinned.

    A missing file and a readable file holding no cells are different facts. ``cells``
    is None only when the file is absent or invalid; ``exists`` distinguishes those two.
    """

    exists: bool
    cells: CellCounts | None


def read_ceiling(cwd: Path) -> Ceiling:
    path = baseline_path(cwd)
    if path.parent.is_symlink() or path.is_symlink():
        return Ceiling(exists=True, cells=None)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Ceiling(exists=False, cells=None)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return Ceiling(exists=True, cells=None)
    return Ceiling(exists=True, cells=parse_cells(raw, cwd))


def write_cells(cwd: Path, cells: CellCountsView) -> None:
    path = baseline_path(cwd)
    if path.parent.is_symlink():
        path.parent.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    serialised_cells = {
        file: {rule: {"count": count} for rule, count in sorted(rules.items()) if count > 0}
        for file, rules in sorted(cells.items())
        if any(count > 0 for count in rules.values())
    }
    payload = {"version": BASELINE_VERSION, "cells": serialised_cells}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def prune_cells(baseline: CellCountsView, current: CellCountsView) -> CellCounts:
    """Lower every cell to what still exists, and never raise one — the only sanctioned
    way for the ceiling to fall. Cells whose violations are all gone disappear."""
    pruned: CellCounts = {}
    for file, rules in baseline.items():
        kept = {rule: min(count, current.get(file, {}).get(rule, 0)) for rule, count in rules.items()}
        kept = {rule: count for rule, count in kept.items() if count > 0}
        if kept:
            pruned[file] = kept
    return pruned


def split_against_baseline(
    current: CellCountsView, baseline: CellCountsView
) -> tuple[CellCounts, dict[RuleId, int]]:
    """Divide today's cells into (excess, held) against the ceiling.

    The ratchet is per file AND per rule: a file with no cell for a rule fails on the next
    violation of it, whatever that rule's total is elsewhere. Excess keeps its file rather
    than collapsing into a rule total — a finding beyond the ceiling is something to go and
    open, and mypy routinely puts it in a file its author never touched, so "3 more
    mypy:arg-type" with no file name is not something anyone can act on. Held totals stay
    per rule because that is what the ledger stores.
    """
    excess: CellCounts = {}
    held: dict[RuleId, int] = {}
    for file, rules in current.items():
        for rule, count in rules.items():
            ceiling = baseline.get(file, {}).get(rule, 0)
            over = max(0, count - ceiling)
            within = min(count, ceiling)
            if over:
                excess.setdefault(file, {})[rule] = over
            if within:
                held[rule] = held.get(rule, 0) + within
    return excess, held


def rule_totals(cells: CellCountsView) -> dict[RuleId, int]:
    totals: dict[RuleId, int] = {}
    for rules in cells.values():
        for rule, count in rules.items():
            totals[rule] = totals.get(rule, 0) + count
    return totals


def analyzers_in(cells: CellCountsView) -> set[str]:
    return {analyzer_of(rule) for rules in cells.values() for rule in rules}


def cells_for(cells: CellCountsView, analyzer: str) -> CellCounts:
    """Only the cells belonging to one analyzer's namespace, files with none omitted."""
    result: CellCounts = {}
    for file, rules in cells.items():
        matching = {rule: count for rule, count in rules.items() if analyzer_of(rule) == analyzer}
        if matching:
            result[file] = matching
    return result


def cells_excluding(cells: CellCountsView, analyzer: str) -> CellCounts:
    """Every cell except one analyzer's namespace, files left with none omitted.

    The complement of `cells_for`: a scoped freeze re-pins one namespace by dropping the old
    one here and merging the freshly measured cells back in.
    """
    result: CellCounts = {}
    for file, rules in cells.items():
        remaining = {rule: count for rule, count in rules.items() if analyzer_of(rule) != analyzer}
        if remaining:
            result[file] = remaining
    return result


def merge_cells(parts: Iterable[CellCountsView]) -> CellCounts:
    """Union several analyzers' cells into one baseline shape.

    Correct namespacing makes the same file x rule impossible to produce from two
    different analyzers, so a collision here means a caller passed overlapping parts —
    the same analyzer's cells twice, say — and that is a bug worth raising loudly rather
    than resolving by silently picking a winner.
    """
    merged: CellCounts = {}
    for part in parts:
        for file, rules in part.items():
            target = merged.setdefault(file, {})
            for rule, count in rules.items():
                if rule in target:
                    raise ValueError(f"cell for file {file!r} x rule {rule!r} appears in more than one part")
                target[rule] = count
    return merged


def finding_total(cells: CellCountsView) -> int:
    return sum(count for rules in cells.values() for count in rules.values())
