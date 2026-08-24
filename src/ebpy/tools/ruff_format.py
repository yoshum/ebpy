"""Formatter detector: configuration detection and diagnosis for ruff/black."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ebpy.models import Gap, ToolSetup
from ebpy.repo.detect.tooling import _dependency_names, _tool_table

from .ruff import has_ruff_config

if TYPE_CHECKING:
    from ebpy.decide.provisioner import FileAction, ProvisionContext
    from ebpy.repo.facts import RepoFacts


def formatter_configured(root_entries: tuple[str, ...], pyproject: dict[str, Any] | None) -> bool:
    """Return True when a formatter (ruff or black) is configured."""
    # Ruff formats as well as lints, so its config settles formatting too.
    deps = _dependency_names(pyproject)
    return (
        has_ruff_config(root_entries, pyproject)
        or _tool_table(pyproject, "black") is not None
        or "black" in deps
    )


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


@dataclass(frozen=True)
class RuffFormatProvisioner:
    """Inert provisioner placeholder for a future standalone formatter (e.g. black).

    Ruff subsumes formatting today, so all operations delegate to RuffProvisioner.
    This class exists so the registry has a named slot for "formatter" provisioning.
    """

    @property
    def name(self) -> str:
        """Unique short identifier for the formatter tool."""
        return "formatter"

    def plan_packages(self, setup: ToolSetup) -> tuple[str, ...]:  # noqa: ARG002
        """Return empty tuple: ruff covers formatting, no additional package needed."""
        return ()

    def plan_file_actions(self, setup: ToolSetup, ctx: ProvisionContext) -> list[FileAction]:  # noqa: ARG002
        """Return empty list: config and the Format check step are owned by RuffProvisioner."""
        return []
