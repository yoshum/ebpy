"""The stable value seam between repository tools and ratchet decisions."""

from __future__ import annotations

from pathlib import Path

from ._values import (
    _DETAIL_LINES as _DETAIL_LINES,
)
from ._values import (
    AnalyzerStatus,
    Failed,
    FailureKind,
    Measured,
    Measurement,
    Observation,
    Unavailable,
    classify,
)
from ..tools import ANALYZER_NAMES, ANALYZERS, ANALYZERS_BY_NAME  # re-export

__all__ = [
    "ANALYZER_NAMES",
    "ANALYZERS",
    "ANALYZERS_BY_NAME",
    "AnalyzerStatus",
    "Failed",
    "FailureKind",
    "Measured",
    "Measurement",
    "Observation",
    "Unavailable",
    "classify",
    "measure_repository",
]


def measure_repository(cwd: Path) -> Measurement:
    """Measure every registered analyzer, retaining partial success as data."""
    return Measurement(analyzers={a.name: a.measure(cwd) for a in ANALYZERS})
