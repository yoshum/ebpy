"""mypy analyzer: execution and conversion to an Observation are contained here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..measurement._mypy import (
    MypyFailedError,
    MypyInvalidOutputError,
    MypyNotFoundError,
    run_mypy_check,
)
from ..measurement._values import Failed, Measured, Observation, Unavailable, _detail, _summary

if TYPE_CHECKING:
    from pathlib import Path

    from ..models import AnalysisMeasurement


@dataclass(frozen=True)
class MypyAnalyzer:
    """mypy analyzer that owns the full observation-building try/except."""

    name: str = "mypy"
    noun: str = "Type errors"

    def measure(self, cwd: Path) -> Observation[AnalysisMeasurement]:
        """Run mypy against the repository at cwd and return the observation."""
        try:
            return Measured(tool="mypy", value=run_mypy_check(cwd))
        except MypyNotFoundError as error:
            return Unavailable(tool="mypy", detail=_detail(error), summary=_summary(error))
        # MypyInvalidOutputError subclasses MypyFailedError, so it must be caught first —
        # otherwise every invalid-output failure would be misreported as execution-failed.
        except MypyInvalidOutputError as error:
            return Failed(
                tool="mypy",
                failure_kind="invalid-output",
                detail=_detail(error),
                summary=_summary(error),
            )
        except (MypyFailedError, OSError) as error:
            return Failed(
                tool="mypy",
                failure_kind="execution-failed",
                detail=_detail(error),
                summary=_summary(error),
            )
