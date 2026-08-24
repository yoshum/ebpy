"""vulture detector: configuration detection and diagnosis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import Gap, ToolSetup
from ..repo.detect.tooling import vulture_configured

if TYPE_CHECKING:
    from ..repo.facts import RepoFacts


@dataclass(frozen=True)
class VultureDetector:
    """Detects whether vulture is configured and reports any gaps."""

    @property
    def name(self) -> str:
        """Unique short identifier for vulture."""
        return "vulture"

    def detect(self, facts: RepoFacts) -> ToolSetup:
        """Return configured=True when vulture is configured or declared as a dependency."""
        return ToolSetup(configured=vulture_configured(facts.pyproject))

    def gaps(self, setup: ToolSetup) -> list[Gap]:
        """Return a tighten gap when vulture is not configured, empty otherwise."""
        if setup.configured:
            return []
        return [
            Gap(
                id="vulture",
                title="No dead-code detection",
                detail="vulture reports unused functions, classes and variables. Report-only at "
                "first; a counter later.",
                phase="tighten",
            )
        ]

    def render_row(self, setup: ToolSetup) -> str:
        """Render a one-line vulture row for the diagnosis table."""
        return f"  vulture           {'yes' if setup.configured else 'no'}"
