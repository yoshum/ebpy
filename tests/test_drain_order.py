from __future__ import annotations

from ebpy.decide.drain_order import (
    build_drain_plan,
    cheapest_first,
    directory_tails,
    heaviest_files,
    rule_spread,
    totals_of,
)
from ebpy.models import Suppression


def entry(file: str, rule: str, count: int) -> Suppression:
    return Suppression(file=file, rule=rule, count=count)


def test_totals_count_distinct_files_and_rules() -> None:
    totals = totals_of([entry("a.py", "E501", 3), entry("a.py", "F401", 1), entry("b.py", "E501", 2)])
    assert (totals.violations, totals.files, totals.rules) == (6, 2, 2)


def test_cheapest_first_is_what_one_edit_can_enforce() -> None:
    ranked = cheapest_first([entry("a.py", "E501", 5), entry("b.py", "F401", 1), entry("c.py", "B008", 2)])
    assert [item.file for item in ranked] == ["b.py", "c.py"]


def test_rules_rank_by_files_to_touch_not_by_violations() -> None:
    # 40 in 3 files and 38 across 31 are the same size in `status` and ten times apart
    # in work — the smaller file count comes first.
    entries = [
        *(entry(f"wide{i}.py", "E501", 2) for i in range(31)),
        *(entry(f"deep{i}.py", "C901", 13) for i in range(3)),
    ]
    assert [spread.rule for spread in rule_spread(entries)] == ["C901", "E501"]


def test_directory_tails_are_the_last_files_carrying_a_rule() -> None:
    entries = [
        entry("src/util/a.py", "E501", 1),
        entry("src/api/b.py", "E501", 1),
        entry("src/api/c.py", "E501", 1),
        entry("src/api/d.py", "E501", 1),
    ]
    tails = directory_tails(entries)
    assert [(tail.directory, len(tail.files)) for tail in tails] == [("src/util", 1)]


def test_a_root_file_reports_a_readable_directory() -> None:
    tails = directory_tails([entry("setup.py", "E501", 1)])
    assert tails[0].directory == "(root)"


def test_heavy_means_one_rule_it_cannot_clear_not_a_large_total() -> None:
    # Two rules at one violation each sums past any cheap threshold while every cell is
    # a quick win — calling that a redesign would contradict `take these first`.
    entries = [entry("light.py", "E501", 1), entry("light.py", "F401", 1), entry("heavy.py", "C901", 9)]
    assert [file.file for file in heaviest_files(entries)] == ["heavy.py"]


def test_a_file_with_one_cheap_rule_and_one_huge_one_appears_in_both_lists() -> None:
    entries = [entry("mixed.py", "F401", 1), entry("mixed.py", "C901", 20)]
    plan = build_drain_plan(entries)
    assert [item.rule for item in plan.take_first] == ["F401"]
    assert [file.file for file in plan.heaviest] == ["mixed.py"]


def test_an_empty_backlog_produces_an_empty_plan() -> None:
    plan = build_drain_plan([])
    assert plan.totals.violations == 0
    assert plan.take_first == ()


def test_next_ranks_ruff_and_mypy_cells_together() -> None:
    # Suppression.rule is an opaque string, so a namespaced mypy cell competes for rank
    # by cost alongside a namespaced ruff cell instead of being sorted into an
    # analyzer-specific bucket.
    entries = [
        entry("a.py", "ruff:F401", 1),
        entry("b.py", "mypy:arg-type", 1),
        entry("c.py", "ruff:C901", 9),
    ]
    ranked = cheapest_first(entries)
    assert [item.rule for item in ranked] == ["ruff:F401", "mypy:arg-type"]


def test_the_plan_serialises_for_json() -> None:
    plan = build_drain_plan([entry("a.py", "E501", 1)], importers={"a.py": 4})
    payload = plan.to_dict()
    assert payload["totals"]["violations"] == 1
    assert payload["importers"] == {"a.py": 4}
