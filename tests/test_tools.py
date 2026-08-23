"""Tests for the tools/ registry contracts."""

from __future__ import annotations

from ebpy.measurement.analyzer import Analyzer


def test_analyzer_protocol_exposes_name_noun_measure() -> None:
    """Analyzer Protocol declares exactly the name, noun, and measure members."""
    assert set(getattr(Analyzer, "__protocol_attrs__", ())) >= {"name", "noun", "measure"}
