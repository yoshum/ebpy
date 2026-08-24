"""mypy analyzer and detector: execution, observation, and configuration detection.

``run_mypy_check`` is re-exported here as the package's measurement seam: the analyzer
resolves it through this namespace so a test can monkeypatch it in one place.
"""

from __future__ import annotations

from ._runner import run_mypy_check
from .analyzer import MypyAnalyzer
from .detector import MypyDetector, MypySetup, mypy_configured, mypy_strict_configured
from .provisioner import MypyProvisioner

__all__ = [
    "MypyAnalyzer",
    "MypyDetector",
    "MypyProvisioner",
    "MypySetup",
    "mypy_configured",
    "mypy_strict_configured",
    "run_mypy_check",
]
