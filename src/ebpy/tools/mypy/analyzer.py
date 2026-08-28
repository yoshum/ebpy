"""mypy analyzer: runs the target repo's mypy and classifies the outcome as an observation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import ebpy.tools.mypy
from ebpy.measurement import Failed, Measured, Observation, Unavailable
from ebpy.models import Language

from ._runner import MypyFailedError, MypyInvalidOutputError, MypyNotFoundError

if TYPE_CHECKING:
    from pathlib import Path

    from ebpy.models import AnalysisMeasurement


@dataclass(frozen=True)
class MypyAnalyzer:
    """mypy analyzer that owns the full observation-building try/except."""

    name: str = "mypy"
    noun: str = "Type errors"
    language: Language = "python"

    def measure(self, cwd: Path) -> Observation[AnalysisMeasurement]:
        """Run mypy against the repository at cwd and return the observation."""
        # Resolve run_mypy_check through the package namespace rather than binding it here, so a
        # test monkeypatching ebpy.tools.mypy.run_mypy_check reaches the call that actually runs.
        try:
            return Measured(tool="mypy", value=ebpy.tools.mypy.run_mypy_check(cwd))
        except MypyNotFoundError as error:
            return Unavailable.from_tool_error("mypy", error)
        # MypyInvalidOutputError subclasses MypyFailedError, so it must be caught first —
        # otherwise every invalid-output failure would be misreported as execution-failed.
        except MypyInvalidOutputError as error:
            return Failed.from_tool_error("mypy", "invalid-output", error)
        except (MypyFailedError, OSError) as error:
            return Failed.from_tool_error("mypy", "execution-failed", error)
