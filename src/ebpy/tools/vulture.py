"""vulture detector and provisioner: configuration detection, diagnosis, and provisioning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ebpy.models import Gap, ToolSetup
from ebpy.repo.detect.tooling import _dependency_names, _tool_table

if TYPE_CHECKING:
    from ebpy.decide.provisioner import FileAction, ProvisionContext
    from ebpy.repo.facts import RepoFacts


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


@dataclass(frozen=True)
class VultureProvisioner:
    """Provisioner for vulture: installs the package; no generated config or CI step today."""

    @property
    def name(self) -> str:
        """Unique short identifier for vulture."""
        return "vulture"

    def plan_packages(self, setup: ToolSetup) -> tuple[str, ...]:
        """Return ("vulture",) when vulture is absent, empty tuple when already configured."""
        return ("vulture",) if not setup.configured else ()

    def plan_file_actions(self, setup: ToolSetup, ctx: ProvisionContext) -> list[FileAction]:
        """Return empty list: vulture has no generated config and no gate step today."""
        return []
