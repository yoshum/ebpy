"""Self-contained analyzer modules for ebpy's built-in tools."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from .mypy import MypyAnalyzer
from .ruff import RuffAnalyzer

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ..measurement.analyzer import Analyzer

# Build via a typed list so mypy can verify Protocol compatibility and infer
# tuple[Analyzer, ...] for ANALYZERS rather than the narrower concrete tuple.
_registry: list[Analyzer] = [RuffAnalyzer(), MypyAnalyzer()]

ANALYZERS: tuple[Analyzer, ...] = tuple(_registry)

ANALYZERS_BY_NAME: Mapping[str, Analyzer] = MappingProxyType({a.name: a for a in ANALYZERS})

# Derived from the registry so the name list cannot drift from the actual set.
ANALYZER_NAMES: tuple[str, ...] = tuple(sorted(ANALYZERS_BY_NAME))
