"""Reading, writing and clamping the v2 baseline, and every way a baseline reads as unreadable."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from ebpy.store.baseline import (
    Ceiling,
    analyzers_in,
    baseline_path,
    cells_excluding,
    cells_for,
    finding_total,
    merge_cells,
    parse_cells,
    prune_cells,
    read_ceiling,
    rule_totals,
    split_against_baseline,
    write_cells,
)
from ebpy.tools.ruff._runner import parse_ruff_json

if TYPE_CHECKING:
    from pathlib import Path

    from ebpy.models import CellCountsView


def test_a_v2_baseline_round_trips_through_write_and_read(tmp_path: Path) -> None:
    write_cells(tmp_path, {"src/a.py": {"ruff:E501": 3}, "src/b.py": {"mypy:arg-type": 2}})
    on_disk = json.loads((tmp_path / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    assert on_disk == {
        "version": 2,
        "cells": {
            "src/a.py": {"ruff:E501": {"count": 3}},
            "src/b.py": {"mypy:arg-type": {"count": 2}},
        },
    }
    assert read_ceiling(tmp_path).cells == {
        "src/a.py": {"ruff:E501": 3},
        "src/b.py": {"mypy:arg-type": 2},
    }


def test_a_clean_v2_baseline_is_distinguishable_from_a_missing_one(tmp_path: Path) -> None:
    """`freeze` decides from this: a repository frozen while clean has a baseline holding
    nothing, and re-freezing it would grandfather everything written since.
    """
    assert read_ceiling(tmp_path) == Ceiling(exists=False, cells=None)
    write_cells(tmp_path, {})
    assert read_ceiling(tmp_path) == Ceiling(exists=True, cells={})


@pytest.mark.parametrize("version", [1, 3, 99, "2"])
def test_an_unknown_version_makes_the_whole_baseline_unreadable(tmp_path: Path, version: object) -> None:
    """A `version` of 1 wrapped like v2 is unreadable too — v1 never carried the key at all."""
    assert parse_cells({"version": version, "cells": {}}, tmp_path) is None


def test_an_extra_top_level_key_makes_the_whole_baseline_unreadable(tmp_path: Path) -> None:
    raw = {"version": 2, "cells": {"src/a.py": {"ruff:E501": {"count": 1}}}, "unexpected": True}
    assert parse_cells(raw, tmp_path) is None


def test_a_v2_rule_without_a_namespace_makes_the_whole_baseline_unreadable(tmp_path: Path) -> None:
    raw = {"version": 2, "cells": {"src/a.py": {"E501": {"count": 1}}}}
    assert parse_cells(raw, tmp_path) is None


@pytest.mark.parametrize("rule", ["ruff:F401\nX", "ruff:F401\rX", "ruff:", ":F401", "F401", ""])
def test_a_malformed_rule_key_makes_the_baseline_unreadable_not_a_crash(tmp_path: Path, rule: str) -> None:
    """A rule key that is not a well-formed namespaced id — carrying a newline, an empty
    half, or no namespace at all — must make the reader return None for corrupt input, never
    a key that makes a later `analyzer_of` raise mid-command.
    """
    raw = {"version": 2, "cells": {"src/a.py": {rule: {"count": 1}}}}
    assert parse_cells(raw, tmp_path) is None


@pytest.mark.parametrize("count", [0, -1, True])
def test_a_zero_or_negative_or_boolean_count_makes_the_baseline_unreadable(
    tmp_path: Path, count: object
) -> None:
    raw = {"version": 2, "cells": {"src/a.py": {"ruff:F401": {"count": count}}}}
    assert parse_cells(raw, tmp_path) is None


def test_two_file_keys_that_collide_after_separator_normalization_are_rejected(tmp_path: Path) -> None:
    raw = {
        "version": 2,
        "cells": {
            "src\\a.py": {"ruff:F401": {"count": 1}},
            "src/a.py": {"ruff:F401": {"count": 1}},
        },
    }
    assert parse_cells(raw, tmp_path) is None


def test_split_against_baseline_keeps_the_file_of_every_excess_cell() -> None:
    # a.py exceeds its ceiling by one; b.py has no ceiling for the rule at all, so its
    # whole count is excess even though the rule's repo-wide total elsewhere is fine.
    current = {"a.py": {"mypy:arg-type": 5}, "b.py": {"mypy:arg-type": 5}}
    baseline = {"a.py": {"mypy:arg-type": 4}}
    excess, _held = split_against_baseline(current, baseline)
    assert excess == {"a.py": {"mypy:arg-type": 1}, "b.py": {"mypy:arg-type": 5}}


def test_split_against_baseline_still_returns_held_totals_per_rule() -> None:
    current = {"a.py": {"ruff:E501": 3}, "b.py": {"ruff:E501": 3}}
    baseline = {"a.py": {"ruff:E501": 4}, "b.py": {"ruff:E501": 4}}
    excess, held = split_against_baseline(current, baseline)
    assert excess == {}
    assert held == {"ruff:E501": 6}


def test_the_writer_always_emits_version_two(tmp_path: Path) -> None:
    write_cells(tmp_path, {})
    on_disk = json.loads((tmp_path / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    assert on_disk == {"version": 2, "cells": {}}


def test_merge_cells_unions_two_namespaces_and_rejects_a_repeated_cell() -> None:
    ruff_cells: CellCountsView = {"a.py": {"ruff:E501": 2}}
    mypy_cells: CellCountsView = {"a.py": {"mypy:arg-type": 1}, "b.py": {"mypy:arg-type": 3}}
    assert merge_cells([ruff_cells, mypy_cells]) == {
        "a.py": {"ruff:E501": 2, "mypy:arg-type": 1},
        "b.py": {"mypy:arg-type": 3},
    }

    with pytest.raises(ValueError, match=r"a\.py.*ruff:E501"):
        merge_cells([{"a.py": {"ruff:E501": 2}}, {"a.py": {"ruff:E501": 3}}])


def test_cells_for_returns_only_one_analyzers_namespace() -> None:
    cells = {
        "a.py": {"ruff:E501": 2, "mypy:arg-type": 1},
        "b.py": {"mypy:arg-type": 3},
    }
    assert cells_for(cells, "mypy") == {"a.py": {"mypy:arg-type": 1}, "b.py": {"mypy:arg-type": 3}}
    assert cells_for(cells, "ruff") == {"a.py": {"ruff:E501": 2}}


def test_cells_excluding_is_the_complement_of_cells_for() -> None:
    cells = {
        "a.py": {"ruff:E501": 2, "mypy:arg-type": 1},
        "b.py": {"mypy:arg-type": 3},
    }
    assert cells_excluding(cells, "mypy") == {"a.py": {"ruff:E501": 2}}
    assert cells_excluding(cells, "ruff") == {"a.py": {"mypy:arg-type": 1}, "b.py": {"mypy:arg-type": 3}}


def test_cells_excluding_drops_a_file_left_with_no_cells() -> None:
    """A file whose only rules all belong to the dropped analyzer vanishes, rather than
    lingering as an empty rule map the merge would then have to reject.
    """
    cells = {"only_mypy.py": {"mypy:arg-type": 3}}
    assert cells_excluding(cells, "mypy") == {}


def test_analyzers_in_names_every_namespace_present() -> None:
    cells = {"a.py": {"ruff:E501": 2, "mypy:arg-type": 1}}
    assert analyzers_in(cells) == {"ruff", "mypy"}


def test_finding_total_sums_every_cell() -> None:
    cells = {
        "a.py": {"ruff:E501": 2, "mypy:arg-type": 1},
        "b.py": {"mypy:arg-type": 3},
    }
    assert finding_total(cells) == 6


def test_prune_lowers_a_cell_to_what_still_exists() -> None:
    pruned = prune_cells({"a.py": {"ruff:E501": 5}}, {"a.py": {"ruff:E501": 2}})
    assert pruned == {"a.py": {"ruff:E501": 2}}


def test_prune_never_raises_a_ceiling() -> None:
    # New violations are the gate's business, not prune's: it can only ever take away.
    pruned = prune_cells({"a.py": {"ruff:E501": 2}}, {"a.py": {"ruff:E501": 9}})
    assert pruned == {"a.py": {"ruff:E501": 2}}


def test_prune_drops_a_file_whose_violations_are_all_gone() -> None:
    assert prune_cells({"a.py": {"ruff:E501": 3}}, {}) == {}


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
        {"src/a.py": {"F401": "one"}},
        {"src/a.py": {"F401": {"count": 1, "extra": "ignored"}}},
        {"version": 2, "cells": {"src/a.py": {}}},
        {"version": 2, "cells": {"src/a.py": {"ruff:F401": "one"}}},
        {"version": 2, "cells": {"src/a.py": {"ruff:F401": {"count": "three"}}}},
        {"version": 2, "cells": {"src/a.py": {"ruff:F401": {"count": True}}}},
    ],
)
def test_a_semantically_malformed_baseline_is_unreadable_as_a_whole(tmp_path: Path, raw: object) -> None:
    path = baseline_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(raw), encoding="utf-8")

    assert read_ceiling(tmp_path) == Ceiling(exists=True, cells=None)


def test_rule_totals_sum_across_files() -> None:
    cells = {"a.py": {"ruff:E501": 2}, "b.py": {"ruff:E501": 3, "ruff:F401": 1}}
    assert rule_totals(cells) == {"ruff:E501": 5, "ruff:F401": 1}


def test_ruff_runner_and_baseline_reader_agree_on_the_cell_key_for_an_absolute_path(tmp_path: Path) -> None:
    """Ruling F: the runner normalizes through `normalize_analyzer_path`, and so must the
    reader, or the same raw finding would land as two different cells depending on which
    side of the ratchet read it.
    """
    absolute_file = str(tmp_path / "src" / "a.py")
    stdout = json.dumps(
        [
            {
                "filename": absolute_file,
                "code": "F401",
                "message": "unused import",
                "location": {"row": 1},
            }
        ]
    )

    measured = parse_ruff_json(stdout, tmp_path)
    stored = parse_cells({"version": 2, "cells": {absolute_file: {"ruff:F401": {"count": 1}}}}, tmp_path)

    assert stored is not None
    assert {file: dict(rules) for file, rules in measured.cells.items()} == stored
