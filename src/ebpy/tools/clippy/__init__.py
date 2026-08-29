"""clippy analyzer and detector: execution, observation, and configuration detection.

``run_clippy_check`` is re-exported here as the package's measurement seam: the analyzer
resolves it through this namespace so a test can monkeypatch it in one place.
"""

from __future__ import annotations

from ._errors import (
    ClippyFailedError,
    ClippyInvalidOutputError,
    ClippyNotFoundError,
    ClippyNoWorkspaceError,
    ClippyUnavailableError,
)
from ._runner import run_clippy_check
from ._topology import RustTopology, RustWorkspace, rust_topology
from .analyzer import ClippyAnalyzer

__all__ = [
    "ClippyAnalyzer",
    "ClippyFailedError",
    "ClippyInvalidOutputError",
    "ClippyNoWorkspaceError",
    "ClippyNotFoundError",
    "ClippyUnavailableError",
    "RustTopology",
    "RustWorkspace",
    "run_clippy_check",
    "rust_topology",
]
