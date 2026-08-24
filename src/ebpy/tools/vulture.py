"""vulture detector: configuration detection and diagnosis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..models import Gap, ToolSetup
from ..repo.detect.tooling import _dependency_names, _tool_table

if TYPE_CHECKING:
    from ..repo.facts import RepoFacts


def vulture_configured(pyproject: dict[str, Any] | None) -> bool:
    """Return True when vulture is configured or declared as a dependency."""
    deps = _dependency_names(pyproject)
    return _tool_table(pyproject, "vulture") is not None or "vulture" in deps


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
