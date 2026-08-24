"""ruff analyzer and detector: execution, observation, and configuration detection.

``run_ruff_check`` is re-exported here as the package's measurement seam: the analyzer
resolves it through this namespace so a test can monkeypatch it in one place.
"""

from __future__ import annotations

from ._runner import run_ruff_check
from .analyzer import RuffAnalyzer
from .detector import RuffDetector, has_ruff_config
from .provisioner import RuffProvisioner

__all__ = [
    "RuffAnalyzer",
    "RuffDetector",
    "RuffProvisioner",
    "has_ruff_config",
    "run_ruff_check",
]
