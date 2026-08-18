"""The ratchet file: ``.ebpy/baseline.json``.

ESLint ships bulk suppressions; Ruff does not, so ebpy carries the equivalent
itself in the same shape ESLint uses — ``{file: {rule: {count}}}``. `freeze`
writes it, `check` compares against it, and `prune` is the only way it falls.
Its size is bounded by rules x files, so reading it whole is safe in a way
reading a log never is.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASELINE_FILE = ".ebpy/baseline.json"

CellCounts = dict[str, dict[str, int]]


def _to_posix(file: str) -> str:
    """Paths are recorded with `/` whatever platform froze the baseline, so a repository
    frozen on Windows groups by the same directory as one frozen on Linux."""
    return file.replace("\\", "/")


def parse_cells(raw: Any) -> CellCounts | None:
    """Parse the complete baseline, rejecting rather than skipping any bad cell."""
    if not isinstance(raw, dict):
        return None
    cells: CellCounts = {}
    for file, rules in raw.items():
        if not isinstance(file, str) or not file or not isinstance(rules, dict) or not rules:
            return None
        parsed_rules: dict[str, int] = {}
        for rule, entry in rules.items():
            if not isinstance(rule, str) or not rule or not isinstance(entry, dict):
                return None
            count = entry.get("count")
            if set(entry) != {"count"} or type(count) is not int or count <= 0:
                return None
            parsed_rules[rule] = count
        normalised = _to_posix(file)
        if normalised in cells:
            return None
        cells[normalised] = parsed_rules
    return cells


def baseline_path(cwd: Path) -> Path:
    return cwd / BASELINE_FILE


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
    return Ceiling(exists=True, cells=parse_cells(raw))


def write_cells(cwd: Path, cells: CellCounts) -> None:
    path = baseline_path(cwd)
    if path.parent.is_symlink():
        path.parent.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    serialised = {
        file: {rule: {"count": count} for rule, count in sorted(rules.items()) if count > 0}
        for file, rules in sorted(cells.items())
        if any(count > 0 for count in rules.values())
    }
    path.write_text(json.dumps(serialised, indent=2) + "\n", encoding="utf-8")


def prune_cells(baseline: CellCounts, current: CellCounts) -> CellCounts:
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
    current: CellCounts, baseline: CellCounts
) -> tuple[dict[str, int], dict[str, int]]:
    """Divide today's violations into (new, grandfathered) per rule.

    The ratchet is per file AND per rule: a file with no cell for a rule fails on the
    next violation of it, whatever that rule's total is elsewhere.
    """
    new: dict[str, int] = {}
    grandfathered: dict[str, int] = {}
    for file, rules in current.items():
        for rule, count in rules.items():
            ceiling = baseline.get(file, {}).get(rule, 0)
            over = max(0, count - ceiling)
            within = min(count, ceiling)
            if over:
                new[rule] = new.get(rule, 0) + over
            if within:
                grandfathered[rule] = grandfathered.get(rule, 0) + within
    return new, grandfathered


def rule_totals(cells: CellCounts) -> dict[str, int]:
    totals: dict[str, int] = {}
    for rules in cells.values():
        for rule, count in rules.items():
            totals[rule] = totals.get(rule, 0) + count
    return totals
