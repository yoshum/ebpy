"""ruff configuration detection and the gap it reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ebpy.models import Gap, ToolSetup
from ebpy.repo.detect.tooling import _tool_table

if TYPE_CHECKING:
    from ebpy.models import Language
    from ebpy.repo.facts import RepoFacts


def has_ruff_config(root_entries: tuple[str, ...], pyproject: dict[str, Any] | None) -> bool:
    """Return True when a ruff config sits at the root or in a [tool.ruff] table."""
    return (
        "ruff.toml" in root_entries
        or ".ruff.toml" in root_entries
        or _tool_table(pyproject, "ruff") is not None
    )


@dataclass(frozen=True)
class RuffDetector:
    """Detects whether ruff is configured and reports any gaps."""

    @property
    def name(self) -> str:
        """Unique short identifier for ruff."""
        return "ruff"

    @property
    def languages(self) -> frozenset[Language]:
        """Ruff is a Python tool."""
        return frozenset({"python"})

    @property
    def requires_repository_setup(self) -> bool:
        """True: ebpy waits for the repository to adopt ruff before proposing to ratchet it."""
        return True

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
