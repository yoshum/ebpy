"""The capability contract that R (the ratchet) depends on.

Detection (configured) is not part of this contract — an uninstalled or
unconfigured tool surfaces via Unavailable or Failed from measure().
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from ebpy.models import AnalysisMeasurement
    from .observation import Observation


class Analyzer(Protocol):
    """An analysis tool that can measure a repository's current violations."""

    @property
    def name(self) -> str:
        """Unique short identifier for the tool (e.g. "ruff")."""
        ...

    @property
    def noun(self) -> str:
        """Human-readable noun for violations this tool finds (e.g. "Lint violations")."""
        ...

    def measure(self, cwd: Path) -> Observation[AnalysisMeasurement]:
        """Run the tool against the repository at cwd and return the observation."""
        ...
