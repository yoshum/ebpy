from __future__ import annotations

import tomllib
from pathlib import Path

from ebpy.detect.ci import detect_ci, missing_runners, unpinned_actions
from ebpy.detect.package_manager import detect_package_manager
from ebpy.detect.sizes import summarize_sizes
from ebpy.detect.tooling import detect_framework, detect_tooling, mypy_strict_configured
from ebpy.diagnose import diagnose
from ebpy.facts import gather_facts
from ebpy.models import SourceFile, WorkflowFile, diagnosis_from_dict


def toml(text: str) -> dict[str, object]:
    return tomllib.loads(text)


def test_a_lockfile_names_the_package_manager() -> None:
    assert detect_package_manager(("uv.lock", "pyproject.toml"), None) == "uv"
    assert detect_package_manager(("poetry.lock",), None) == "poetry"


def test_a_poetry_table_counts_when_the_lockfile_is_absent() -> None:
    assert detect_package_manager(("pyproject.toml",), toml("[tool.poetry]\nname='x'\n")) == "poetry"


def test_a_bare_repo_falls_back_to_pip() -> None:
    assert detect_package_manager((), None) == "pip"


def test_ruff_is_detected_from_either_config_location() -> None:
    from_pyproject = detect_tooling(("pyproject.toml",), toml("[tool.ruff]\nline-length=100\n"), {}, "")
    assert from_pyproject.ruff
    assert detect_tooling(("ruff.toml",), None, {}, "").ruff


def test_ruff_settles_formatting_too() -> None:
    # `ruff format` comes with the config; a repo with Ruff is not missing a formatter.
    assert detect_tooling(("ruff.toml",), None, {}, "").formatter


def test_mypy_strict_is_read_from_pyproject_and_from_ini() -> None:
    assert mypy_strict_configured(toml("[tool.mypy]\nstrict = true\n"), {})
    assert mypy_strict_configured(None, {"mypy.ini": "[mypy]\nstrict = True\n"})
    assert not mypy_strict_configured(toml("[tool.mypy]\nstrict = false\n"), {})


def test_pytest_counts_as_configured_when_it_is_only_a_dependency() -> None:
    tooling = detect_tooling((), toml('[dependency-groups]\ndev = ["pytest>=8"]\n'), {}, "")
    assert tooling.pytest


def test_poetry_dev_groups_are_read_for_dependencies() -> None:
    pyproject = toml('[tool.poetry.group.dev.dependencies]\nvulture = "^2"\n')
    assert detect_tooling((), pyproject, {}, "").vulture


def test_secret_scanning_is_found_in_a_workflow_or_a_pre_commit_hook() -> None:
    assert detect_tooling((), None, {}, "uses: gitleaks").secret_scanning
    assert detect_tooling((), None, {".pre-commit-config.yaml": "repo: detect-secrets"}, "").secret_scanning
    assert not detect_tooling((), None, {}, "uses: actions/checkout@v4").secret_scanning


def test_agent_instructions_are_listed_in_order() -> None:
    tooling = detect_tooling(("AGENTS.md", "CLAUDE.md"), None, {}, "")
    assert tooling.agent_instructions == ("CLAUDE.md", "AGENTS.md")


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
    assert (coverage.runs_lint, coverage.runs_typecheck, coverage.runs_test, coverage.runs_ebpy_check) == (
        True,
        True,
        True,
        True,
    )


def test_thorough_ci_without_the_gate_enforces_nothing() -> None:
    coverage = detect_ci((WorkflowFile(path="ci.yml", content="- run: pytest\n"),))
    assert coverage.runs_test
    assert not coverage.runs_ebpy_check


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
    diagnosis = diagnose(gather_facts(tmp_path))
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
    diagnosis = diagnose(gather_facts(tmp_path))
    ids = {gap.id for gap in diagnosis.gaps}
    assert {"ruff", "mypy", "pytest", "secret-scan", "ci"} <= ids


def test_a_configured_repository_reports_no_bootstrap_gaps(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 100\n\n[tool.mypy]\nstrict = true\n\n[tool.pytest.ini_options]\n",
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("rules\n", encoding="utf-8")
    (tmp_path / ".gitleaks.toml").write_text("", encoding="utf-8")
    diagnosis = diagnose(gather_facts(tmp_path))
    assert [gap.id for gap in diagnosis.gaps if gap.phase == "bootstrap"] == []


def test_mypy_present_but_loose_is_a_tighten_gap_not_a_bootstrap_one(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.mypy]\nstrict = false\n", encoding="utf-8")
    diagnosis = diagnose(gather_facts(tmp_path))
    gap = next(gap for gap in diagnosis.gaps if gap.id == "mypy-strict")
    assert gap.phase == "tighten"


def test_a_diagnosis_survives_a_round_trip_through_json(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n', encoding="utf-8")
    diagnosis = diagnose(gather_facts(tmp_path))
    restored = diagnosis_from_dict(diagnosis.to_dict())
    assert restored == diagnosis
