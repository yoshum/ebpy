"""Tests for the tools/ registry contracts."""

from __future__ import annotations

from ebpy.cell_key import is_analyzer_name
from ebpy.measurement.analyzer import Analyzer
from ebpy.tools import ANALYZER_NAMES, ANALYZERS, ANALYZERS_BY_NAME


def test_analyzer_protocol_exposes_name_noun_measure() -> None:
    """Analyzer Protocol declares exactly the name, noun, and measure members."""
    assert set(getattr(Analyzer, "__protocol_attrs__", ())) >= {"name", "noun", "measure"}


def test_registry_lists_ruff_and_mypy_with_valid_names() -> None:
    """ANALYZERS contains exactly ruff and mypy, with valid names and non-empty nouns."""
    names = tuple(a.name for a in ANALYZERS)
    assert set(names) == {"ruff", "mypy"}
    assert all(is_analyzer_name(a.name) for a in ANALYZERS)
    assert all(a.noun for a in ANALYZERS)  # noun is non-empty
    assert set(ANALYZERS_BY_NAME) == set(names)
    assert tuple(sorted(names)) == ANALYZER_NAMES
