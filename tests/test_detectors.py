"""Tests for ToolDetector contract types (ToolSetup, MypySetup)."""

from __future__ import annotations

from ebpy.repo.detect.detector import MypySetup, ToolSetup


def test_toolsetup_carries_configured_and_mypysetup_adds_strict() -> None:
    """MypySetup is a ToolSetup and exposes both fields with correct values."""
    assert ToolSetup(configured=True).configured is True
    s = MypySetup(configured=True, strict=False)
    assert (s.configured, s.strict) == (True, False)
    assert isinstance(s, ToolSetup)  # 派生は基底の .configured を必ず持つ
