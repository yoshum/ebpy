"""The ratchet file: ``.ebpy/baseline.json``.

ESLint ships bulk suppressions; Ruff does not, so ebpy carries the equivalent
itself in the same shape ESLint uses — ``{file: {rule: {count}}}``. `freeze`
writes it, `check` compares against it, and `prune` is the only way it falls.
Its size is bounded by rules x files, so reading it whole is safe in a way
reading a log never is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Suppression

BASELINE_FILE = ".ebpy/baseline.json"

CellCounts = dict[str, dict[str, int]]


def _to_posix(file: str) -> str:
    """Paths are recorded with `/` whatever platform froze the baseline, so a repository
    frozen on Windows groups by the same directory as one frozen on Linux."""
    return file.replace("\\", "/")


def parse_suppressions(raw: Any) -> list[Suppression]:
    if not isinstance(raw, dict):
        return []
    entries: list[Suppression] = []
    for file, rules in raw.items():
        if not isinstance(rules, dict):
            continue
        for rule, entry in rules.items():
            if isinstance(entry, dict) and isinstance(entry.get("count"), int):
                entries.append(Suppression(file=_to_posix(str(file)), rule=str(rule), count=entry["count"]))
    return entries


def baseline_path(cwd: Path) -> Path:
    return cwd / BASELINE_FILE


def read_suppressions(cwd: Path) -> list[Suppression]:
    try:
        raw = json.loads(baseline_path(cwd).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return parse_suppressions(raw)


def read_suppression_total(cwd: Path) -> int:
    return sum(entry.count for entry in read_suppressions(cwd))


def read_cells(cwd: Path) -> CellCounts:
    return cells_of(read_suppressions(cwd))


def cells_of(entries: list[Suppression]) -> CellCounts:
    cells: CellCounts = {}
    for entry in entries:
        cells.setdefault(entry.file, {})[entry.rule] = entry.count
    return cells


def write_cells(cwd: Path, cells: CellCounts) -> None:
    path = baseline_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
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


def total_of(counts: dict[str, int]) -> int:
    return sum(counts.values())
