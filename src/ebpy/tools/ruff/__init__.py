"""ruff analyzer and detector: execution, observation, and configuration detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...decide.provisioner import FileAction
from ...generate.configs import ruff_pyproject_section, ruff_toml_content
from ...measurement import Failed, Measured, Observation, Unavailable
from ...models import Gap, ToolSetup
from ...repo.detect.tooling import _tool_table
from ._runner import (
    RuffFailedError,
    RuffInvalidOutputError,
    RuffNotFoundError,
    run_ruff_check,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ...models import AnalysisMeasurement
    from ...repo.facts import RepoFacts


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

    def packages(self, setup: ToolSetup) -> tuple[str, ...]:
        """Return ("ruff",) when ruff is absent, empty tuple when already configured."""
        return ("ruff",) if not setup.configured else ()

    def config_actions(self, setup: ToolSetup, has_pyproject: bool, target_version: str) -> list[FileAction]:
        """Append a [tool.ruff] section to pyproject.toml, or create ruff.toml when there is no pyproject."""
        if setup.configured:
            return []
        if has_pyproject:
            return [
                FileAction(
                    path="pyproject.toml",
                    content="\n" + ruff_pyproject_section(target_version),
                    mode="append",
                    reason="lint + format config; the rule tiers the ratchet will freeze",
                )
            ]
        return [
            FileAction(
                path="ruff.toml",
                content=ruff_toml_content(target_version),
                mode="create",
                reason="lint + format config (no pyproject.toml to append to)",
            )
        ]

    def workflow_steps(self, run_prefix: str) -> list[str]:
        """Return the Format check CI step lines, matching the gate_workflow output."""
        return [
            "      - name: Format check",
            f"        run: {run_prefix}ruff format --check .",
        ]


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
