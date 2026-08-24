"""The stable value seam between repository tools and ratchet decisions.

This is an abstract leaf: it names the observation value types and the Analyzer
contract, and imports nothing from the concrete ``tools`` runners that satisfy it.
"""

from __future__ import annotations

from .analyzer import Analyzer
from .observation import (
    AnalyzerStatus,
    Failed,
    FailureKind,
    Measured,
    Measurement,
    Observation,
    Unavailable,
    classify,
)

__all__ = [
    "Analyzer",
    "AnalyzerStatus",
    "Failed",
    "FailureKind",
    "Measured",
    "Measurement",
    "Observation",
    "Unavailable",
    "classify",
]
