"""Detecting the package manager, tools and CI, and sizing the backlog into each phase's gaps."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ebpy._toml import loads
from ebpy.decide.diagnose import diagnose
from ebpy.models import SourceFile, ToolSetup, WorkflowFile, diagnosis_from_dict
from ebpy.repo.detect.ci import detect_ci, missing_runners, unpinned_actions
from ebpy.repo.detect.package_manager import detect_package_manager
from ebpy.repo.detect.sizes import summarize_sizes
from ebpy.repo.detect.tooling import detect_agent_instructions, detect_framework
from ebpy.repo.facts import gather_facts
from ebpy.tools.gitleaks import secret_scan_configured
from ebpy.tools.mypy import mypy_strict_configured
from ebpy.tools.pytest import pytest_configured
from ebpy.tools.ruff import has_ruff_config
from ebpy.tools.ruff_format import formatter_configured
from ebpy.tools.vulture import vulture_configured

if TYPE_CHECKING:
    from pathlib import Path


def toml(text: str) -> dict[str, object]:
    return loads(text)


def test_a_lockfile_names_the_package_manager() -> None:
    assert detect_package_manager(("uv.lock", "pyproject.toml"), None) == "uv"
    assert detect_package_manager(("poetry.lock",), None) == "poetry"


def test_a_poetry_table_counts_when_the_lockfile_is_absent() -> None:
    assert detect_package_manager(("pyproject.toml",), toml("[tool.poetry]\nname='x'\n")) == "poetry"


def test_a_bare_repo_falls_back_to_pip() -> None:
    assert detect_package_manager((), None) == "pip"


def test_ruff_is_detected_from_either_config_location() -> None:
    assert has_ruff_config(("pyproject.toml",), toml("[tool.ruff]\nline-length=100\n"))
    assert has_ruff_config(("ruff.toml",), None)


def test_ruff_settles_formatting_too() -> None:
    # `ruff format` comes with the config; a repo with Ruff is not missing a formatter.
    assert formatter_configured(("ruff.toml",), None)


def test_mypy_strict_is_read_from_pyproject_and_from_ini() -> None:
    assert mypy_strict_configured(toml("[tool.mypy]\nstrict = true\n"), {})
    assert mypy_strict_configured(None, {"mypy.ini": "[mypy]\nstrict = True\n"})
    assert not mypy_strict_configured(toml("[tool.mypy]\nstrict = false\n"), {})


def test_pytest_counts_as_configured_when_it_is_only_a_dependency() -> None:
    assert pytest_configured((), toml('[dependency-groups]\ndev = ["pytest>=8"]\n'), {})


def test_poetry_dev_groups_are_read_for_dependencies() -> None:
    pyproject = toml('[tool.poetry.group.dev.dependencies]\nvulture = "^2"\n')
    assert vulture_configured(pyproject)


def test_secret_scanning_is_found_in_a_workflow_or_a_pre_commit_hook() -> None:
    assert secret_scan_configured((), "uses: gitleaks", "")
    assert secret_scan_configured((), "", "repo: detect-secrets")
    assert not secret_scan_configured((), "uses: actions/checkout@v4", "")


def test_agent_instructions_are_listed_in_order() -> None:
    assert detect_agent_instructions(("AGENTS.md", "CLAUDE.md")) == ("CLAUDE.md", "AGENTS.md")


def test_a_framework_is_detected_by_dependency() -> None:
    assert detect_framework(toml('[project]\ndependencies = ["fastapi>=0.1"]\n')) == "fastapi"
    assert detect_framework(toml("[project]\ndependencies = []\n")) == "none"


def test_ci_runners_come_from_the_workflow_text_not_its_filename() -> None:
    workflows = (
        WorkflowFile(path=".github/workflows/windows-daily.yaml", content="runs-on: ubuntu-latest\n"),
    )
    assert detect_ci(workflows).runners == ("ubuntu-latest",)


def test_ci_steps_are_recognised() -> None:
    content = "runs-on: ubuntu-latest\n- run: ruff check .\n- run: mypy .\n- run: pytest\n- run: ebpy check\n"
    coverage = detect_ci((WorkflowFile(path="ci.yml", content=content),))
    assert (
        coverage.runs_lint,
        coverage.runs_typecheck,
        coverage.runs_test,
        coverage.runs_ebpy_check,
    ) == (
        True,
        True,
        True,
        True,
    )


def test_the_gate_counts_as_running_lint_and_typecheck() -> None:
    """A workflow that runs the gate counts as running lint and typecheck.

    `ebpy check` measures ruff and mypy through the seam, so a workflow that runs it
    covers lint and typecheck without a separate `ruff check` or `mypy` step — which the
    ratchet model omits deliberately, since a raw step demands zero violations.
    """
    coverage = detect_ci((WorkflowFile(path="ci.yml", content="- run: pytest\n- run: ebpy check\n"),))
    assert coverage.runs_lint
    assert coverage.runs_typecheck


def test_thorough_ci_without_the_gate_enforces_nothing() -> None:
    coverage = detect_ci((WorkflowFile(path="ci.yml", content="- run: pytest\n"),))
    assert coverage.runs_test
    assert not coverage.runs_ebpy_check
    assert not coverage.runs_lint
    assert not coverage.runs_typecheck


def test_a_tag_is_not_a_pin() -> None:
    content = "steps:\n  - uses: actions/checkout@v4\n  - uses: astral-sh/setup-uv@main\n"
    coverage = detect_ci((WorkflowFile(path="ci.yml", content=content),))
    assert coverage.unpinned_actions == ("actions/checkout@v4", "astral-sh/setup-uv@main")


def test_a_commit_pin_survives_the_version_comment_beside_it() -> None:
    content = f"  - uses: actions/checkout@{'1' * 40} # v4.4.0\n"
    assert unpinned_actions((WorkflowFile(path="ci.yml", content=content),)) == ()


def test_local_and_container_steps_are_not_counted_as_unpinned() -> None:
    # Neither resolves through a moveable git ref, so neither is a pin anybody can tighten.
    content = "  - uses: ./.github/actions/setup\n  - uses: docker://alpine:3.19\n"
    assert unpinned_actions((WorkflowFile(path="ci.yml", content=content),)) == ()


def test_a_repo_without_workflows_reports_no_pins_rather_than_clean_ones() -> None:
    # Empty here means "nothing was looked at", and `present` is what tells them apart.
    coverage = detect_ci(())
    assert coverage.unpinned_actions == ()
    assert not coverage.present


def test_unpinned_actions_are_reported_as_a_gap(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("  - uses: actions/checkout@v4\n", encoding="utf-8")
    diagnosis = diagnose(gather_facts(tmp_path), ())
    gap = next(gap for gap in diagnosis.gaps if gap.id == "ci-action-pins")
    assert "actions/checkout@v4" in gap.detail


def test_missing_runners_names_the_platforms_never_exercised() -> None:
    coverage = detect_ci((WorkflowFile(path="ci.yml", content="runs-on: ubuntu-latest"),))
    assert missing_runners(coverage) == ["macos", "windows"]


def test_sizes_report_the_backlog_before_any_limit_is_switched_on() -> None:
    files = (SourceFile(path="big.py", lines=900), SourceFile(path="small.py", lines=10))
    sizes = summarize_sizes(files)
    assert (sizes.total, sizes.over_file_limit) == (2, 1)
    assert sizes.largest[0].path == "big.py"


def test_a_bare_repository_produces_a_gap_for_everything(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    diagnosis = diagnose(gather_facts(tmp_path), ())
    ids = {gap.id for gap in diagnosis.gaps}
    assert {"ruff", "mypy", "pytest", "secret-scan", "ci"} <= ids


def test_a_configured_repository_reports_no_bootstrap_gaps(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 100\n\n[tool.mypy]\nstrict = true\n\n[tool.pytest.ini_options]\n",
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("rules\n", encoding="utf-8")
    (tmp_path / ".gitleaks.toml").write_text("", encoding="utf-8")
    diagnosis = diagnose(gather_facts(tmp_path), ())
    assert [gap.id for gap in diagnosis.gaps if gap.phase == "bootstrap"] == []


def test_mypy_present_but_loose_is_a_tighten_gap_not_a_bootstrap_one(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.mypy]\nstrict = false\n", encoding="utf-8")
    diagnosis = diagnose(gather_facts(tmp_path), ())
    gap = next(gap for gap in diagnosis.gaps if gap.id == "mypy-strict")
    assert gap.phase == "tighten"


def test_the_mypy_gap_describes_per_cell_ratcheting_not_a_counter(tmp_path: Path) -> None:
    """The mypy gap describes per-cell ratcheting, not a global counter.

    Mypy is now ratcheted per file per rule, the same as Ruff — not as one global error
    counter. The gap the user reads must describe today's model, so the retired "counter"
    wording is refused here where it would otherwise slip past CI unpinned.
    """
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    diagnosis = diagnose(gather_facts(tmp_path), ())
    gap = next(gap for gap in diagnosis.gaps if gap.id == "mypy")
    assert "per file per rule" in gap.detail
    assert "counter" not in gap.detail


def test_a_diagnosis_survives_a_round_trip_through_json(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n', encoding="utf-8")
    diagnosis = diagnose(gather_facts(tmp_path), ())
    restored = diagnosis_from_dict(diagnosis.to_dict())
    # Every setup reads back as a base ToolSetup: subtype provenance (mypy's strictness) is
    # regenerated on the next diagnose, so the round trip preserves only `configured`.
    expected = replace(
        diagnosis,
        tool_setups={
            name: ToolSetup(configured=setup.configured) for name, setup in diagnosis.tool_setups.items()
        },
    )
    assert restored == expected


def test_a_configured_analyzer_outside_the_roster_becomes_an_unratcheted_gap(tmp_path: Path) -> None:
    """A configured but unfrozen analyzer is reported, as a tighten gap, to run without a ceiling.

    Once the analyzer is in the roster the gap is gone.
    """
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")

    unrostered = {gap.id for gap in diagnose(gather_facts(tmp_path), ()).gaps}
    assert "unratcheted:ruff" in unrostered

    rostered = {gap.id for gap in diagnose(gather_facts(tmp_path), ("ruff",)).gaps}
    assert "unratcheted:ruff" not in rostered


def test_a_non_analyzer_tool_never_becomes_an_unratcheted_gap(tmp_path: Path) -> None:
    """A configured formatter or pytest is never reported as configured-but-unratcheted.

    Only ruff and mypy can be ratcheted; the other tools are report-only.
    """
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 100\n\n[tool.pytest.ini_options]\n", encoding="utf-8"
    )
    gap_ids = {gap.id for gap in diagnose(gather_facts(tmp_path), ("ruff",)).gaps}
    assert not any(gap_id.startswith("unratcheted:") for gap_id in gap_ids)
