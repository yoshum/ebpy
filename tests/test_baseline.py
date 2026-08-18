from __future__ import annotations

import json
from pathlib import Path

import pytest

from ebpy.baseline import (
    Ceiling,
    baseline_path,
    parse_cells,
    prune_cells,
    read_ceiling,
    rule_totals,
    split_against_baseline,
    write_cells,
)


def test_parse_reads_the_file_rule_count_shape() -> None:
    cells = parse_cells({"src/a.py": {"E501": {"count": 3}, "F401": {"count": 1}}})
    assert cells == {"src/a.py": {"E501": 3, "F401": 1}}


def test_windows_paths_normalise_so_a_repo_groups_the_same_either_way() -> None:
    assert parse_cells({"src\\pkg\\a.py": {"E501": {"count": 2}}}) == {"src/pkg/a.py": {"E501": 2}}


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
    assert read_ceiling(tmp_path).cells == {"src/a.py": {"E501": 3}}


def test_a_missing_baseline_and_an_empty_one_are_different_facts(tmp_path: Path) -> None:
    """`freeze` decides from this: a repository frozen while clean has a baseline holding
    nothing, and re-freezing it would grandfather everything written since."""
    assert read_ceiling(tmp_path) == Ceiling(exists=False, cells=None)
    write_cells(tmp_path, {})
    assert read_ceiling(tmp_path) == Ceiling(exists=True, cells={})


def test_the_ceiling_carries_the_cells_it_validated(tmp_path: Path) -> None:
    write_cells(tmp_path, {"a.py": {"E501": 2}, "b.py": {"F401": 3}})
    assert read_ceiling(tmp_path) == Ceiling(
        exists=True,
        cells={"a.py": {"E501": 2}, "b.py": {"F401": 3}},
    )


def test_a_baseline_that_cannot_be_parsed_is_unreadable_not_empty(tmp_path: Path) -> None:
    """Conflict markers must not look like a clean frozen baseline."""
    path = baseline_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<<<<<<< HEAD\n{}\n=======\n{}\n>>>>>>> other\n", encoding="utf-8")
    assert read_ceiling(tmp_path) == Ceiling(exists=True, cells=None)


def test_a_baseline_with_invalid_utf8_is_unreadable_not_missing(tmp_path: Path) -> None:
    """A decoding failure is as unreadable as invalid JSON and must fail closed."""
    path = baseline_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe")

    assert read_ceiling(tmp_path) == Ceiling(exists=True, cells=None)


@pytest.mark.parametrize("target_exists", [False, True])
def test_a_baseline_symlink_is_always_unreadable(tmp_path: Path, target_exists: bool) -> None:
    target = tmp_path / "outside-baseline.json"
    if target_exists:
        target.write_text("{}\n", encoding="utf-8")
    path = baseline_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.symlink_to(target)

    assert read_ceiling(tmp_path) == Ceiling(exists=True, cells=None)


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {"src/a.py": {}},
        {"src/a.py": {"F401": {"count": 0}}},
        {"src/a.py": {"F401": {"count": True}}},
        {"src/a.py": {"F401": {"count": 1, "extra": "ignored"}}},
        {"src/a.py": {"F401": "one"}},
        {
            "src\\a.py": {"F401": {"count": 1}},
            "src/a.py": {"F401": {"count": 1}},
        },
    ],
)
def test_a_semantically_malformed_baseline_is_unreadable_as_a_whole(tmp_path: Path, raw: object) -> None:
    path = baseline_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(raw), encoding="utf-8")

    assert read_ceiling(tmp_path) == Ceiling(exists=True, cells=None)


def test_rule_totals_sum_across_files() -> None:
    cells = {"a.py": {"E501": 2}, "b.py": {"E501": 3, "F401": 1}}
    assert rule_totals(cells) == {"E501": 5, "F401": 1}
