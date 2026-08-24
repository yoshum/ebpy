"""Static registries of ebpy's built-in tool capabilities (analyzers, detectors, provisioners)."""

from __future__ import annotations

from .registry import (
    ANALYZER_NAMES,
    ANALYZERS,
    ANALYZERS_BY_NAME,
    DETECTORS,
    DETECTORS_BY_NAME,
    PROVISIONERS,
    PROVISIONERS_BY_NAME,
    measure_repository,
)

__all__ = [
    "ANALYZERS",
    "ANALYZERS_BY_NAME",
    "ANALYZER_NAMES",
    "DETECTORS",
    "DETECTORS_BY_NAME",
    "PROVISIONERS",
    "PROVISIONERS_BY_NAME",
    "measure_repository",
]
