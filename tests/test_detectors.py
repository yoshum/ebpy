"""Tests for ToolDetector contract types (ToolSetup, MypySetup)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ebpy.repo.detect.detector import MypySetup, ToolSetup
from ebpy.repo.facts import RepoFacts
from ebpy.tools.mypy import MypyDetector
from ebpy.tools.ruff import RuffDetector


def _facts(
    pyproject: dict[str, Any] | None = None,
    root_entries: tuple[str, ...] = (),
    configs: dict[str, str] | None = None,
) -> RepoFacts:
    return RepoFacts(
        cwd=Path("."),
        root_entries=tuple(root_entries),
        all_files=(),
        pyproject=pyproject,
        source_files=(),
        workflows=(),
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
