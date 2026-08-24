"""ruff analyzer and detector: execution, observation, and configuration detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ebpy.decide.provisioner import AddWorkflowStep, AppendText, CreateFile
from ebpy.generate.configs import ruff_pyproject_section, ruff_toml_content
from ebpy.measurement import Failed, Measured, Observation, Unavailable
from ebpy.models import Gap, ToolSetup
from ebpy.repo.detect.tooling import _tool_table

from ._runner import (
    RuffFailedError,
    RuffInvalidOutputError,
    RuffNotFoundError,
    run_ruff_check,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ebpy.decide.provisioner import FileAction, ProvisionContext
    from ebpy.models import AnalysisMeasurement
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


@dataclass(frozen=True)
class RuffAnalyzer:
    """ruff analyzer that owns the full observation-building try/except."""

    name: str = "ruff"
    noun: str = "Lint violations"

    def measure(self, cwd: Path) -> Observation[AnalysisMeasurement]:
        """Run ruff against the repository at cwd and return the observation."""
        try:
            return Measured(tool="ruff", value=run_ruff_check(cwd))
        except RuffNotFoundError as error:
            return Unavailable.from_tool_error("ruff", error)
        except RuffInvalidOutputError as error:
            return Failed.from_tool_error("ruff", "invalid-output", error)
        except (RuffFailedError, OSError) as error:
            return Failed.from_tool_error("ruff", "execution-failed", error)
