"""Static registries of ebpy's built-in tool capabilities (analyzers and detectors)."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from ..measurement import Measurement
from .gitleaks import GitleaksDetector
from .mypy import MypyAnalyzer, MypyDetector
from .pytest import PytestDetector
from .ruff import RuffAnalyzer, RuffDetector
from .ruff_format import RuffFormatDetector
from .vulture import VultureDetector

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from ..measurement import Analyzer
    from ..repo.detect.detector import ToolDetector

# Build via a typed list so mypy can verify Protocol compatibility and infer
# tuple[Analyzer, ...] for ANALYZERS rather than the narrower concrete tuple.
_registry: list[Analyzer] = [RuffAnalyzer(), MypyAnalyzer()]

ANALYZERS: tuple[Analyzer, ...] = tuple(_registry)

ANALYZERS_BY_NAME: Mapping[str, Analyzer] = MappingProxyType({a.name: a for a in ANALYZERS})

# Derived from the registry so the name list cannot drift from the actual set.
ANALYZER_NAMES: tuple[str, ...] = tuple(sorted(ANALYZERS_BY_NAME))

# Build via a typed list so mypy can verify Protocol compatibility and infer
# tuple[ToolDetector[Any], ...] for DETECTORS rather than the narrower concrete tuple.
# Any is required for the type parameter because the registry is heterogeneous:
# most detectors use ToolSetup but MypyDetector uses MypySetup, and S appears
# in both covariant (detect return) and contravariant (gaps/render_row parameter)
# positions, making ToolDetector invariant in S.
_detectors: list[ToolDetector[Any]] = [
    RuffDetector(),
    MypyDetector(),
    RuffFormatDetector(),
    PytestDetector(),
    VultureDetector(),
    GitleaksDetector(),
]

DETECTORS: tuple[ToolDetector[Any], ...] = tuple(_detectors)

DETECTORS_BY_NAME: Mapping[str, ToolDetector[Any]] = MappingProxyType({d.name: d for d in DETECTORS})


def measure_repository(cwd: Path) -> Measurement:
    """Measure every registered analyzer, retaining partial success as data."""
    return Measurement(analyzers={a.name: a.measure(cwd) for a in ANALYZERS})
