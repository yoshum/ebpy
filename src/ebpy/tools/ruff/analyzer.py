"""ruff analyzer: runs the target repo's ruff and classifies the outcome as an observation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import ebpy.tools.ruff
from ebpy.measurement import Failed, Measured, Observation, Unavailable

from ._runner import RuffFailedError, RuffInvalidOutputError, RuffNotFoundError

if TYPE_CHECKING:
    from pathlib import Path

    from ebpy.models import AnalysisMeasurement


@dataclass(frozen=True)
class RuffAnalyzer:
    """ruff analyzer that owns the full observation-building try/except."""

    name: str = "ruff"
    noun: str = "Lint violations"

    def measure(self, cwd: Path) -> Observation[AnalysisMeasurement]:
        """Run ruff against the repository at cwd and return the observation."""
        # Resolve run_ruff_check through the package namespace rather than binding it here, so a
        # test monkeypatching ebpy.tools.ruff.run_ruff_check reaches the call that actually runs.
        try:
            return Measured(tool="ruff", value=ebpy.tools.ruff.run_ruff_check(cwd))
        except RuffNotFoundError as error:
            return Unavailable.from_tool_error("ruff", error)
        except RuffInvalidOutputError as error:
            return Failed.from_tool_error("ruff", "invalid-output", error)
        except (RuffFailedError, OSError) as error:
            return Failed.from_tool_error("ruff", "execution-failed", error)
