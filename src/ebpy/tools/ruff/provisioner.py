"""ruff provisioner: installs the package, writes the config, and adds the CI format-check step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ebpy.decide.provisioner import AddWorkflowStep, AppendText, CreateFile
from ebpy.generate.configs import ruff_pyproject_section, ruff_toml_content

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
        """Write the config when unconfigured, then always the Format check gate step."""
        actions: list[FileAction] = []
        if not setup.configured:
            if ctx.has_pyproject:
                actions.append(
                    AppendText(
                        path="pyproject.toml",
                        content="\n" + ruff_pyproject_section(ctx.target_version),
                        reason="lint + format config; the rule tiers the ratchet will freeze",
                    )
                )
            else:
                actions.append(
                    CreateFile(
                        path="ruff.toml",
                        content=ruff_toml_content(ctx.target_version),
                        reason="lint + format config (no pyproject.toml to append to)",
                    )
                )
        actions.append(
            AddWorkflowStep(
                lines=("      - name: Format check", f"        run: {ctx.run_prefix}ruff format --check .")
            )
        )
        return actions
