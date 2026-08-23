"""The capability contract that R (the ratchet) depends on.

Detection (configured) is not part of this contract — an uninstalled or
unconfigured tool surfaces via Unavailable or Failed from measure().
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from ..models import AnalysisMeasurement
    from ._values import Observation


class Analyzer(Protocol):
    """An analysis tool that can measure a repository's current violations."""

    name: str
    noun: str

    def measure(self, cwd: Path) -> Observation[AnalysisMeasurement]:
        """Run the tool against the repository at cwd and return the observation."""
        ...
