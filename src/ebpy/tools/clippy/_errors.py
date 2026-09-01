"""The failures clippy measurement can end in, one per observation the seam can hold.

Three layers, as ruff and mypy have: unavailable, failed, and failed-because-unreadable.
Unavailable has two subclasses rather than one because two genuinely different situations
end there — cargo cannot be executed, and cargo resolved no workspace at all — and calling
the second one "not found" would be a claim the name cannot support.
"""

from __future__ import annotations

from ebpy.errors import ToolError


class ClippyUnavailableError(ToolError):
    """clippy cannot measure this repository at all, so there is nothing to observe."""


class ClippyNotFoundError(ClippyUnavailableError):
    """cargo, or the clippy component, cannot be executed here."""


class ClippyNoWorkspaceError(ClippyUnavailableError):
    """cargo resolved no workspace in this repository, so clippy has nothing to run against."""


class ClippyFailedError(ToolError):
    """clippy ran and did not produce a usable measurement."""


class ClippyInvalidOutputError(ClippyFailedError):
    """clippy produced output ebpy could not read — a different fact from clippy failing."""
