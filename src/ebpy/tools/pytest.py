"""pytest detector: configuration detection and diagnosis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import Gap, ToolSetup
from ..repo.detect.tooling import pytest_configured

if TYPE_CHECKING:
    from ..repo.facts import RepoFacts


@dataclass(frozen=True)
class PytestDetector:
    """Detects whether pytest is configured and reports any gaps."""

    @property
    def name(self) -> str:
        """Unique short identifier for pytest."""
        return "pytest"

    def detect(self, facts: RepoFacts) -> ToolSetup:
        """Return configured=True when pytest is configured via any standard mechanism."""
        return ToolSetup(
            configured=pytest_configured(facts.root_entries, facts.pyproject, facts.extra_config_text)
        )

    def gaps(self, setup: ToolSetup) -> list[Gap]:
        """Return a bootstrap gap when no test runner is configured, empty otherwise."""
        if setup.configured:
            return []
        return [
            Gap(
                id="pytest",
                title="No test runner",
                detail="Draining violations finds bugs. Without a runner there is nowhere to pin them.",
                phase="bootstrap",
            )
        ]

    def render_row(self, setup: ToolSetup) -> str:
        """Render a one-line pytest row for the diagnosis table."""
        return f"  pytest            {'yes' if setup.configured else 'no'}"
