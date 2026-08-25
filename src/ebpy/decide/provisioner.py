"""Tool-provisioning (P) contract: what to install and what file actions a tool needs.

A provisioner declares outcomes, not mechanisms: the file actions it needs as a small
closed union. Bootstrap planning realizes them. The action types live here so both the
planner and the concrete tool provisioners can import them without a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ebpy.models import ToolSetup


@dataclass(frozen=True)
class CreateFile:
    """Write a new file the tool owns outright."""

    path: str
    content: str
    reason: str


@dataclass(frozen=True)
class AppendText:
    """Append text to a (possibly existing) file — e.g. a [tool.x] section into pyproject.toml."""

    path: str
    content: str
    reason: str


@dataclass(frozen=True)
class AddWorkflowStep:
    """Contribute step lines into the ebpy-owned gate workflow (quality.yml).

    A gate step is not a self-contained file: it must be spliced at a fixed position inside
    jobs.quality.steps. The applier owns quality.yml's skeleton and splices these lines in.
    """

    lines: tuple[str, ...]


FileAction = CreateFile | AppendText | AddWorkflowStep


@dataclass(frozen=True)
class ProvisionContext:
    """Repo/composition facts a provisioner needs to build its actions.

    Facts, not any one tool's dialect: ``requires_python`` is carried raw, exactly as the
    repository declares it, and a provisioner that needs it in its own tool's spelling
    translates it itself.
    """

    has_pyproject: bool
    requires_python: str | None
    run_prefix: str  # e.g. "uv run " / "poetry run " / "" for plain pip


class Provisioner(Protocol):
    """Contract for a single-tool provisioner that bootstrap planning delegates to."""

    @property
    def name(self) -> str:
        """Unique short identifier for the tool (e.g. "ruff")."""
        ...

    def plan_packages(self, setup: ToolSetup) -> tuple[str, ...]:
        """Return packages to install given the tool's current setup state."""
        ...

    def plan_file_actions(self, setup: ToolSetup, ctx: ProvisionContext) -> list[FileAction]:
        """Return the file actions this tool needs (configs, owned files, gate steps)."""
        ...
