"""Formatter detector: configuration detection and diagnosis for ruff/black."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import Gap
from ..repo.detect.detector import ToolSetup
from ..repo.detect.tooling import formatter_configured

if TYPE_CHECKING:
    from ..repo.facts import RepoFacts


@dataclass(frozen=True)
class RuffFormatDetector:
    """Detects whether a formatter (ruff or black) is configured and reports any gaps."""

    @property
    def name(self) -> str:
        """Unique short identifier for the formatter tool."""
        return "formatter"

    def detect(self, facts: RepoFacts) -> ToolSetup:
        """Return configured=True when ruff or black is configured in the repository."""
        return ToolSetup(configured=formatter_configured(facts.root_entries, facts.pyproject))

    def gaps(self, setup: ToolSetup) -> list[Gap]:
        """Return a bootstrap gap when no formatter is configured, empty otherwise."""
        if setup.configured:
            return []
        return [
            Gap(
                id="formatter",
                title="No formatter",
                detail="Formatting must land before linting starts, or the first drain PR is a diff "
                "nobody can read. `ruff format` comes free with the Ruff config.",
                phase="bootstrap",
            )
        ]

    def render_row(self, setup: ToolSetup) -> str:
        """Render a one-line formatter row for the diagnosis table."""
        return f"  formatter         {'yes' if setup.configured else 'no'}"
