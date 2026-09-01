"""pytest detector and provisioner: configuration detection, diagnosis, and provisioning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ebpy.decide.provisioner import AddWorkflowStep
from ebpy.models import Gap, ToolSetup
from ebpy.repo.detect.tooling import _dependency_names, _ini_has_section, _tool_table

if TYPE_CHECKING:
    from ebpy.decide.provisioner import FileAction, ProvisionContext
    from ebpy.models import Language
    from ebpy.repo.facts import RepoFacts


def pytest_configured(
    root_entries: tuple[str, ...],
    pyproject: dict[str, Any] | None,
    configs: dict[str, str],
) -> bool:
    """Return True when pytest is configured via any standard mechanism."""
    deps = _dependency_names(pyproject)
    return (
        _tool_table(pyproject, "pytest") is not None
        or "pytest.ini" in root_entries
        or _ini_has_section(configs.get("tox.ini"), "pytest")
        or _ini_has_section(configs.get("setup.cfg"), "tool:pytest")
        or "pytest" in deps
    )


@dataclass(frozen=True)
class PytestDetector:
    """Detects whether pytest is configured and reports any gaps."""

    @property
    def name(self) -> str:
        """Unique short identifier for pytest."""
        return "pytest"

    @property
    def languages(self) -> frozenset[Language]:
        """Pytest is a Python tool."""
        return frozenset({"python"})

    def detect(self, facts: RepoFacts) -> ToolSetup:
        """Return configured=True when pytest is configured via any standard mechanism."""
        return ToolSetup(
            configured=pytest_configured(facts.root_entries, facts.pyproject, facts.extra_config_text)
        )

    def gaps(self, setup: ToolSetup) -> list[Gap]:
        """Return a bootstrap gap when no test runner is configured, empty otherwise."""
        if setup.configured:
            return []
        return [
            Gap(
                id="pytest",
                title="No test runner",
                detail="Draining violations finds bugs. Without a runner there is nowhere to pin them.",
                phase="bootstrap",
            )
        ]

    def render_row(self, setup: ToolSetup) -> str:
        """Render a one-line pytest row for the diagnosis table."""
        return f"  pytest            {'yes' if setup.configured else 'no'}"


@dataclass(frozen=True)
class PytestProvisioner:
    """Provisioner for pytest: installs the package and adds the Test CI step."""

    @property
    def name(self) -> str:
        """Unique short identifier for pytest."""
        return "pytest"

    def plan_packages(self, setup: ToolSetup) -> tuple[str, ...]:
        """Return ("pytest",) when pytest is absent, empty tuple when already configured."""
        return ("pytest",) if not setup.configured else ()

    def plan_file_actions(self, setup: ToolSetup, ctx: ProvisionContext) -> list[FileAction]:
        """Return the Test gate step (pytest needs no generated config file)."""
        return [AddWorkflowStep(lines=("      - name: Test", f"        run: {ctx.run_prefix}pytest"))]
