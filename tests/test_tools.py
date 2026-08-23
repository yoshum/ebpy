"""Tests for the tools/ registry contracts."""

from __future__ import annotations

import subprocess
import sys

from ebpy.cell_key import is_analyzer_name
from ebpy.measurement.analyzer import Analyzer
from ebpy.tools import ANALYZER_NAMES, ANALYZERS, ANALYZERS_BY_NAME, DETECTORS, DETECTORS_BY_NAME


def test_analyzer_protocol_exposes_name_noun_measure() -> None:
    """Analyzer Protocol declares exactly the name, noun, and measure members."""
    assert {m for m in dir(Analyzer) if not m.startswith("_")} == {"name", "noun", "measure"}


def test_tools_package_imports_without_measurement_preloaded() -> None:
    """ebpy.tools and its submodules must be importable in a fresh interpreter.

    The import cycle tools → measurement._* → measurement → tools caused an
    ImportError when ebpy.tools was the first ebpy package touched.  This test
    spawns a clean interpreter so pytest's own import order cannot mask the bug.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import ebpy.tools; import ebpy.tools.mypy; import ebpy.tools.ruff"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_detectors_registry_lists_all_tools() -> None:
    """DETECTORS contains exactly the six expected tools; DETECTORS_BY_NAME keys match."""
    names = {d.name for d in DETECTORS}
    assert names == {"ruff", "mypy", "formatter", "pytest", "vulture", "secret-scan"}
    assert set(DETECTORS_BY_NAME) == names


def test_registry_lists_ruff_and_mypy_with_valid_names() -> None:
    """ANALYZERS contains exactly ruff and mypy, with valid names and non-empty nouns."""
    names = tuple(a.name for a in ANALYZERS)
    assert set(names) == {"ruff", "mypy"}
    assert all(is_analyzer_name(a.name) for a in ANALYZERS)
    assert all(a.noun for a in ANALYZERS)  # noun is non-empty
    assert set(ANALYZERS_BY_NAME) == set(names)
    assert tuple(sorted(names)) == ANALYZER_NAMES
