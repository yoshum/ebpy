"""Tool-provisioning (P) contract: what to install, what config to write, what CI steps to add.

The action types live here so both bootstrap planning and concrete tool provisioners
can import them without a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from ..repo.detect.detector import ToolSetup


@dataclass(frozen=True)
class FileAction:
    """A single file write or append that a provisioner requests."""

    path: str
    content: str
    # append: pyproject.toml gains a section under the configs that already exist in it.
    mode: Literal["create", "append"]
    reason: str


@dataclass(frozen=True)
class InstallAction:
    """A package-manager install command that a provisioner requests."""

    packages: tuple[str, ...]
    argv: tuple[str, ...]


class Provisioner(Protocol):
    """Contract for a single-tool provisioner that bootstrap planning delegates to."""

    @property
    def name(self) -> str:
        """Unique short identifier for the tool (e.g. "ruff")."""
        ...

    def packages(self, setup: ToolSetup) -> tuple[str, ...]:
        """Return packages to install given the tool's current setup state."""
        ...

    def config_actions(self, setup: ToolSetup, has_pyproject: bool, target_version: str) -> list[FileAction]:
        """Return file actions needed to configure the tool (empty if already configured)."""
        ...

    def workflow_steps(self, run_prefix: str) -> list[str]:
        """Return CI workflow step lines for this tool (e.g. ``["uv run ruff check ."]``)."""
        ...
