from __future__ import annotations

from ebpy.lint_report import area_of, build_lint_report, matrix_from_cells, matrix_from_suppressions
from ebpy.models import Suppression
from ebpy.render.lint_report import render_lint_report


def test_a_root_file_belongs_to_a_named_area_not_an_empty_one() -> None:
    assert area_of("setup.py") == "(root)"
    assert area_of("src/pkg/a.py") == "src"


def test_the_matrix_folds_files_up_into_their_area() -> None:
    matrix = matrix_from_cells({"src/a.py": {"E501": 2}, "src/b.py": {"E501": 1}, "tests/c.py": {"F401": 4}})
    assert matrix == {"src": {"E501": 3}, "tests": {"F401": 4}}


def test_the_matrix_reads_the_same_from_the_ratchet_file() -> None:
    entries = [Suppression(file="src/a.py", rule="E501", count=2)]
    assert matrix_from_suppressions(entries) == {"src": {"E501": 2}}


def test_areas_are_ordered_by_weight_so_the_shape_is_visible() -> None:
    report = build_lint_report(
        new_by_rule={},
        backlog_matrix={"small": {"E501": 1}, "big": {"E501": 30}},
        mypy_errors=0,
        files_with_findings=2,
        lint_failure=None,
    )
    assert report.sections[0].areas == ("big", "small")


def test_new_violations_get_their_own_section() -> None:
    report = build_lint_report(
        new_by_rule={"E501": 3},
        backlog_matrix={},
        mypy_errors=None,
        files_with_findings=1,
        lint_failure=None,
    )
    rendered = render_lint_report(report)
    assert "## New violations" in rendered
    assert "`E501` | 3" in rendered


def test_nobody_looked_reads_differently_from_no_debt() -> None:
    looked = render_lint_report(
        build_lint_report(
            new_by_rule={}, backlog_matrix={}, mypy_errors=0, files_with_findings=4, lint_failure=None
        )
    )
    did_not = render_lint_report(
        build_lint_report(
            new_by_rule=None,
            backlog_matrix={},
            mypy_errors=None,
            files_with_findings=0,
            lint_failure="ruff is not installed here",
        )
    )
    assert "Ruff did not run" in did_not
    assert "ruff is not installed here" in did_not
    assert "Ruff did not run" not in looked


def test_unmeasured_mypy_is_not_reported_as_zero() -> None:
    rendered = render_lint_report(
        build_lint_report(
            new_by_rule={}, backlog_matrix={}, mypy_errors=None, files_with_findings=1, lint_failure=None
        )
    )
    assert "mypy errors: **not measured**" in rendered


def test_the_report_serialises_for_json() -> None:
    report = build_lint_report(
        new_by_rule={"E501": 1},
        backlog_matrix={"src": {"F401": 2}},
        mypy_errors=7,
        files_with_findings=3,
        lint_failure=None,
    )
    payload = report.to_dict()
    assert payload["newTotal"] == 1
    assert payload["backlogTotal"] == 2
    assert payload["mypyErrors"] == 7
    assert payload["sections"][0]["rows"][0]["rule"] == "F401"
