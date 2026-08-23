"""ruff analyzer and detector: execution, observation, and configuration detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...measurement import Failed, Measured, Observation, Unavailable
from ...models import Gap
from ...repo.detect.detector import ToolSetup
from ...repo.detect.tooling import has_ruff_config
from ._runner import (
    RuffFailedError,
    RuffInvalidOutputError,
    RuffNotFoundError,
    run_ruff_check,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ...models import AnalysisMeasurement
    from ...repo.facts import RepoFacts


@dataclass(frozen=True)
class RuffDetector:
    """Detects whether ruff is configured and reports any gaps."""

    @property
    def name(self) -> str:
        """Unique short identifier for ruff."""
        return "ruff"

    def detect(self, facts: RepoFacts) -> ToolSetup:
        """Return configured=True when a ruff config is present in the repository root."""
        return ToolSetup(configured=has_ruff_config(facts.root_entries, facts.pyproject))

    def gaps(self, setup: ToolSetup) -> list[Gap]:
        """Return a bootstrap gap when ruff is not configured, empty otherwise."""
        if setup.configured:
            return []
        return [
            Gap(
                id="ruff",
                title="Ruff is not configured",
                detail="Nothing enforces anything yet. This is the first thing bootstrap installs — "
                "one tool covers linting, import order and formatting.",
                phase="bootstrap",
            )
        ]

    def render_row(self, setup: ToolSetup) -> str:
        """Render a one-line ruff row for the diagnosis table."""
        return f"  ruff              {'yes' if setup.configured else 'no'}"


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
