"""ruff provisioner: installs the package, writes the config, and adds the CI format-check step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ebpy.decide.provisioner import AddWorkflowStep, AppendText, CreateFile, WithheldConfig

from .config import ruff_pyproject_section, ruff_target_version, ruff_toml_content

if TYPE_CHECKING:
    from ebpy.decide.provisioner import FileAction, ProvisionContext
    from ebpy.models import ToolSetup


@dataclass(frozen=True)
class RuffProvisioner:
    """Provisioner for ruff: installs the package, writes the config, and adds the CI format-check step."""

    @property
    def name(self) -> str:
        """Unique short identifier for ruff."""
        return "ruff"

    def plan_packages(self, setup: ToolSetup) -> tuple[str, ...]:
        """Return ("ruff",) when ruff is absent, empty tuple when already configured."""
        return ("ruff",) if not setup.configured else ()

    def plan_file_actions(self, setup: ToolSetup, ctx: ProvisionContext) -> list[FileAction]:
        """Write the config when unconfigured, withhold it when configured, then the Format check step.

        The config is built either way: a repository that already configures ruff still needs to
        see what ebpy would have written, or nothing tells it which rule tiers the ratchet expects.
        """
        target_version = ruff_target_version(ctx.requires_python)
        config: CreateFile | AppendText
        if ctx.has_pyproject:
            config = AppendText(
                path="pyproject.toml",
                content="\n" + ruff_pyproject_section(target_version),
                reason="lint + format config; the rule tiers the ratchet will freeze",
            )
        else:
            config = CreateFile(
                path="ruff.toml",
                content=ruff_toml_content(target_version),
                reason="lint + format config (no pyproject.toml to append to)",
            )

        actions: list[FileAction] = [
            WithheldConfig(config, "ruff is already configured") if setup.configured else config
        ]
        actions.append(
            AddWorkflowStep(
                lines=("      - name: Format check", f"        run: {ctx.run_prefix}ruff format --check .")
            )
        )
        return actions
