from __future__ import annotations

import json
from pathlib import Path

from ebpy.baseline import (
    cells_of,
    parse_suppressions,
    prune_cells,
    read_suppressions,
    split_against_baseline,
    write_cells,
)
from ebpy.models import Suppression


def test_parse_reads_the_file_rule_count_shape() -> None:
    entries = parse_suppressions({"src/a.py": {"E501": {"count": 3}, "F401": {"count": 1}}})
    assert sorted((e.rule, e.count) for e in entries) == [("E501", 3), ("F401", 1)]


def test_windows_paths_normalise_so_a_repo_groups_the_same_either_way() -> None:
    entries = parse_suppressions({"src\\pkg\\a.py": {"E501": {"count": 2}}})
    assert entries[0].file == "src/pkg/a.py"


def test_malformed_entries_are_skipped_rather_than_crashing() -> None:
    entries = parse_suppressions({"src/a.py": {"E501": "three"}, "src/b.py": 7})
    assert entries == []


def test_the_ratchet_is_per_file_and_per_rule() -> None:
    # 3 in a.py is at its ceiling; 1 in b.py has no ceiling at all, so it is new —
    # even though the rule's repo-wide total (4) equals the repo-wide ceiling.
    current = {"a.py": {"E501": 3}, "b.py": {"E501": 1}}
    baseline = {"a.py": {"E501": 4}}
    new, grandfathered = split_against_baseline(current, baseline)
    assert new == {"E501": 1}
    assert grandfathered == {"E501": 3}


def test_a_count_below_its_ceiling_is_not_new() -> None:
    new, grandfathered = split_against_baseline({"a.py": {"E501": 1}}, {"a.py": {"E501": 4}})
    assert new == {}
    assert grandfathered == {"E501": 1}


def test_prune_lowers_a_cell_to_what_still_exists() -> None:
    pruned = prune_cells({"a.py": {"E501": 5}}, {"a.py": {"E501": 2}})
    assert pruned == {"a.py": {"E501": 2}}


def test_prune_never_raises_a_ceiling() -> None:
    # New violations are the gate's business, not prune's: it can only ever take away.
    pruned = prune_cells({"a.py": {"E501": 2}}, {"a.py": {"E501": 9}})
    assert pruned == {"a.py": {"E501": 2}}


def test_prune_drops_a_file_whose_violations_are_all_gone() -> None:
    assert prune_cells({"a.py": {"E501": 3}}, {}) == {}


def test_cells_round_trip_through_disk(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/a.py": {"E501": 3}, "src/b.py": {"F401": 0}})
    written = json.loads((tmp_path / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    # A zero cell is not a ceiling, it is the absence of one — writing it would
    # grandfather a file that has nothing to grandfather.
    assert written == {"src/a.py": {"E501": {"count": 3}}}
    assert read_suppressions(tmp_path) == [Suppression(file="src/a.py", rule="E501", count=3)]


def test_a_missing_baseline_reads_as_empty(tmp_path: Path) -> None:
    assert read_suppressions(tmp_path) == []


def test_cells_of_regroups_entries_by_file() -> None:
    entries = [
        Suppression(file="a.py", rule="E501", count=2),
        Suppression(file="a.py", rule="F401", count=1),
    ]
    assert cells_of(entries) == {"a.py": {"E501": 2, "F401": 1}}
