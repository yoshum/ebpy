"""clippy analyzer: runs cargo clippy and classifies the outcome as an observation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import ebpy.tools.clippy
from ebpy.measurement import Failed, Measured, Observation, Unavailable

from ._errors import ClippyFailedError, ClippyInvalidOutputError, ClippyUnavailableError

if TYPE_CHECKING:
    from pathlib import Path

    from ebpy.models import AnalysisMeasurement, Language


@dataclass(frozen=True)
class ClippyAnalyzer:
    """clippy analyzer that owns the full observation-building try/except."""

    name: str = "clippy"
    # Not "Clippy lints": rustc's own lints (`unused_variables` and friends) arrive in the
    # same stream and earn cells too, so the noun names what is found, not what found it.
    noun: str = "Rust lint warnings"
    language: Language = "rust"

    def measure(self, cwd: Path) -> Observation[AnalysisMeasurement]:
        """Run clippy against the repository at cwd and return the observation."""
        # Resolved through the package namespace rather than bound here, so a test
        # monkeypatching ebpy.tools.clippy.run_clippy_check reaches the call that runs.
        try:
            return Measured(tool="clippy", value=ebpy.tools.clippy.run_clippy_check(cwd))
        except ClippyUnavailableError as error:
            return Unavailable.from_tool_error("clippy", error)
        # ClippyInvalidOutputError subclasses ClippyFailedError, so it must be caught first —
        # otherwise every invalid-output failure would be misreported as execution-failed.
        except ClippyInvalidOutputError as error:
            return Failed.from_tool_error("clippy", "invalid-output", error)
        except (ClippyFailedError, OSError) as error:
            return Failed.from_tool_error("clippy", "execution-failed", error)
