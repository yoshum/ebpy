"""ruff analyzer: execution and conversion to an Observation are contained here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..measurement._ruff import (
    RuffFailedError,
    RuffInvalidOutputError,
    RuffNotFoundError,
    run_ruff_check,
)
from ..measurement._values import Failed, Measured, Observation, Unavailable, _detail, _summary

if TYPE_CHECKING:
    from pathlib import Path

    from ..models import AnalysisMeasurement


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
            return Unavailable(tool="ruff", detail=_detail(error), summary=_summary(error))
        except RuffInvalidOutputError as error:
            return Failed(
                tool="ruff",
                failure_kind="invalid-output",
                detail=_detail(error),
                summary=_summary(error),
            )
        except (RuffFailedError, OSError) as error:
            return Failed(
                tool="ruff",
                failure_kind="execution-failed",
                detail=_detail(error),
                summary=_summary(error),
            )
