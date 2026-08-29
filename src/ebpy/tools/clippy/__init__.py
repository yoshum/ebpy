"""clippy analyzer and detector: execution, observation, and configuration detection."""

from __future__ import annotations

from ._errors import (
    ClippyFailedError,
    ClippyInvalidOutputError,
    ClippyNotFoundError,
    ClippyNoWorkspaceError,
    ClippyUnavailableError,
)
from ._topology import RustTopology, RustWorkspace, rust_topology

__all__ = [
    "ClippyFailedError",
    "ClippyInvalidOutputError",
    "ClippyNoWorkspaceError",
    "ClippyNotFoundError",
    "ClippyUnavailableError",
    "RustTopology",
    "RustWorkspace",
    "rust_topology",
]
