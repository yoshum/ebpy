"""ruff analyzer: execution and conversion to an Observation are contained here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...measurement import Failed, Measured, Observation, Unavailable
from ._runner import (
    RuffFailedError,
    RuffInvalidOutputError,
    RuffNotFoundError,
    run_ruff_check,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ...models import AnalysisMeasurement


@dataclass(frozen=True)
class RuffAnalyzer:
    """ruff analyzer that owns the full observation-building try/except."""

    name: str = "ruff"
    noun: str = "Lint violations"

    def measure(self, cwd: Path) -> Observation[AnalysisMeasurement]:
        """Run ruff against the repository at cwd and return the observation."""
        try:
            return Measured(tool="ruff", value=run_ruff_check(cwd))
        except RuffNotFoundError as error:
            return Unavailable.from_tool_error("ruff", error)
        except RuffInvalidOutputError as error:
            return Failed.from_tool_error("ruff", "invalid-output", error)
        except (RuffFailedError, OSError) as error:
            return Failed.from_tool_error("ruff", "execution-failed", error)
