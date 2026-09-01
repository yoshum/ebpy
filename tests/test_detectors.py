"""Tests for ToolDetector contract types (ToolSetup, MypySetup)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ebpy.models import ToolSetup, WorkflowFile
from ebpy.repo.facts import RepoFacts
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


def test_gitleaks_declares_no_language_because_it_is_repository_wide() -> None:
    """Empty `languages` means "always runs": gitleaks reads workflows and configs, no source."""
    assert GitleaksDetector().languages == frozenset()
