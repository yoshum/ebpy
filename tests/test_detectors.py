"""Tests for ToolDetector contract types (ToolSetup, MypySetup)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ebpy.models import ToolSetup, WorkflowFile
from ebpy.repo.facts import RepoFacts, gather_facts
from ebpy.tools.clippy import ClippyDetector, ClippySetup
from ebpy.tools.gitleaks import GitleaksDetector
from ebpy.tools.mypy import MypyDetector, MypySetup
from ebpy.tools.pytest import PytestDetector
from ebpy.tools.ruff import RuffDetector
from ebpy.tools.ruff_format import RuffFormatDetector
from ebpy.tools.vulture import VultureDetector


def _facts(
    pyproject: dict[str, Any] | None = None,
    root_entries: tuple[str, ...] = (),
    configs: dict[str, str] | None = None,
    workflows: tuple[WorkflowFile, ...] = (),
) -> RepoFacts:
    return RepoFacts(
        cwd=Path("."),
        root_entries=tuple(root_entries),
        all_files=(),
        pyproject=pyproject,
        source_files=(),
        workflows=workflows,
        extra_config_text=configs or {},
    )


def test_toolsetup_carries_configured_and_mypysetup_adds_strict() -> None:
    """MypySetup is a ToolSetup and exposes both fields with correct values."""
    assert ToolSetup(configured=True).configured is True
    s = MypySetup(configured=True, strict=False)
    assert (s.configured, s.strict) == (True, False)
    assert isinstance(s, ToolSetup)  # derived class must expose .configured from the base


def test_ruff_detector_reads_config_presence() -> None:
    """RuffDetector.detect returns configured=True when a ruff table is present in pyproject."""
    assert RuffDetector().detect(_facts(pyproject={"tool": {"ruff": {}}})).configured is True
    assert RuffDetector().detect(_facts()).configured is False


def test_mypy_detector_reports_strict() -> None:
    """MypyDetector.detect captures both configured and strict fields from pyproject."""
    s = MypyDetector().detect(_facts(pyproject={"tool": {"mypy": {"strict": True}}}))
    assert (s.configured, s.strict) == (True, True)
    s2 = MypyDetector().detect(_facts(pyproject={"tool": {"mypy": {}}}))
    assert (s2.configured, s2.strict) == (True, False)


def test_ruff_format_detector_detects_ruff_config() -> None:
    """RuffFormatDetector.detect returns configured=True when ruff config is present."""
    assert RuffFormatDetector().detect(_facts(pyproject={"tool": {"ruff": {}}})).configured is True
    assert RuffFormatDetector().detect(_facts()).configured is False


def test_pytest_detector_detects_config() -> None:
    """PytestDetector.detect returns configured=True when a pytest table is present in pyproject."""
    assert PytestDetector().detect(_facts(pyproject={"tool": {"pytest": {}}})).configured is True
    assert PytestDetector().detect(_facts()).configured is False


def test_vulture_detector_detects_config() -> None:
    """VultureDetector.detect returns configured=True when a vulture table is present in pyproject."""
    assert VultureDetector().detect(_facts(pyproject={"tool": {"vulture": {}}})).configured is True
    assert VultureDetector().detect(_facts()).configured is False


def test_gitleaks_detector_detects_workflow_mention() -> None:
    """GitleaksDetector.detect returns configured=True when gitleaks appears in a workflow file."""
    workflow = WorkflowFile(path=".github/workflows/ci.yml", content="uses: gitleaks/gitleaks-action@v2")
    assert GitleaksDetector().detect(_facts(workflows=(workflow,))).configured is True
    assert GitleaksDetector().detect(_facts()).configured is False


def test_a_cargo_manifest_alone_does_not_make_clippy_configured(tmp_path: Path) -> None:
    """`configured` claims the repository configured clippy, not that it contains Rust."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert not ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_lint_table_makes_clippy_configured(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[lints.clippy]\nall='warn'\n", encoding="utf-8")
    assert ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_workspace_lint_table_makes_clippy_configured(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[workspace.lints.clippy]\nall='warn'\n", encoding="utf-8")
    assert ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_non_table_clippy_lints_value_does_not_configure_clippy(tmp_path: Path) -> None:
    """The lint-table rule counts only a `dict` value; `clippy = "warn"` is not a table."""
    (tmp_path / "Cargo.toml").write_text("[lints]\nclippy = 'warn'\n", encoding="utf-8")
    assert not ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_clippy_toml_above_a_manifest_makes_clippy_configured(tmp_path: Path) -> None:
    (tmp_path / "clippy.toml").write_text("msrv = '1.79'\n", encoding="utf-8")
    (tmp_path / "crates" / "a").mkdir(parents=True)
    (tmp_path / "crates" / "a" / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_clippy_toml_below_every_manifest_does_not_configure_the_repository(tmp_path: Path) -> None:
    """One fixture file must not mark a whole repository configured."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "clippy.toml").write_text("", encoding="utf-8")
    assert not ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_ci_step_running_clippy_makes_it_configured(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n  a:\n    steps:\n      - run: cargo clippy\n", encoding="utf-8"
    )
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_toolchain_qualified_ci_step_is_recognised(tmp_path: Path) -> None:
    """`cargo +nightly clippy` is a normal CI spelling a naive regex misses."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("      - run: cargo +nightly clippy -- -D warnings\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_an_unreadable_manifest_is_named_in_its_own_gap(tmp_path: Path) -> None:
    """Aggregating them into one gap makes it impossible to see which are still broken."""
    (tmp_path / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    (tmp_path / "crates").mkdir()
    (tmp_path / "crates" / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    gaps = ClippyDetector().gaps(ClippyDetector().detect(gather_facts(tmp_path)))
    assert [g.id for g in gaps] == ["clippy-manifest:Cargo.toml", "clippy-manifest:crates/Cargo.toml"]


def test_an_unconfigured_clippy_reports_no_gap_at_all(tmp_path: Path) -> None:
    """Clippy needs no repository configuration and has no provisioner, so such a gap cannot close."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert ClippyDetector().gaps(ClippyDetector().detect(gather_facts(tmp_path))) == []


def test_an_invalid_manifest_and_a_configured_clippy_coexist(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[lints.clippy]\nall='warn'\n", encoding="utf-8")
    (tmp_path / "crates").mkdir()
    (tmp_path / "crates" / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    setup = ClippyDetector().detect(gather_facts(tmp_path))
    assert setup.configured
    assert len(setup.invalid_manifests) == 1


def test_a_manifest_ebpy_could_parse_never_crashes_detection(tmp_path: Path) -> None:
    """A value that parsed as TOML is not thereby a table: `workspace = "x"` must not raise."""
    (tmp_path / "Cargo.toml").write_text("workspace = 'x'\n\n[package]\nname = 'a'\n", encoding="utf-8")
    setup = ClippyDetector().detect(gather_facts(tmp_path))
    assert isinstance(setup, ClippySetup)


def test_the_clippy_row_says_it_runs_without_configuration(tmp_path: Path) -> None:
    """Unlike the other six tools, clippy still works unconfigured; the row must not imply otherwise."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    row = ClippyDetector().render_row(ClippyDetector().detect(gather_facts(tmp_path)))
    assert "runs with defaults" in row


def test_the_five_python_detectors_declare_the_python_language() -> None:
    """ruff, formatter, mypy, pytest and vulture all belong to Python and only Python."""
    detectors = (
        RuffDetector(),
        RuffFormatDetector(),
        MypyDetector(),
        PytestDetector(),
        VultureDetector(),
    )
    for detector in detectors:
        assert detector.languages == frozenset({"python"})


def test_clippy_declares_the_rust_language() -> None:
    assert ClippyDetector().languages == frozenset({"rust"})


def test_gitleaks_declares_no_language_because_it_is_repository_wide() -> None:
    """Empty `languages` means "always runs": gitleaks reads workflows and configs, no source."""
    assert GitleaksDetector().languages == frozenset()
