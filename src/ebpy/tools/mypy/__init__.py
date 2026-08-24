"""mypy analyzer: execution and conversion to an Observation are contained here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...measurement import Failed, Measured, Observation, Unavailable
from ._runner import (
    MypyFailedError,
    MypyInvalidOutputError,
    MypyNotFoundError,
    run_mypy_check,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ...models import AnalysisMeasurement


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
            return Unavailable.from_tool_error("mypy", error)
        # MypyInvalidOutputError subclasses MypyFailedError, so it must be caught first —
        # otherwise every invalid-output failure would be misreported as execution-failed.
        except MypyInvalidOutputError as error:
            return Failed.from_tool_error("mypy", "invalid-output", error)
        except (MypyFailedError, OSError) as error:
            return Failed.from_tool_error("mypy", "execution-failed", error)
