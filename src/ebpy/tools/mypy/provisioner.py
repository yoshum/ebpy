"""mypy provisioner: installs the package and writes strict type-checking config."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ebpy.decide.provisioner import AppendText, CreateFile
from ebpy.generate.configs import MYPY_INI_CONTENT, MYPY_PYPROJECT_SECTION

if TYPE_CHECKING:
    from ebpy.decide.provisioner import FileAction, ProvisionContext
    from ebpy.models import ToolSetup


@dataclass(frozen=True)
class MypyProvisioner:
    """Provisioner for mypy: installs the package and writes strict type-checking config."""

    @property
    def name(self) -> str:
        """Unique short identifier for mypy."""
        return "mypy"

    def plan_packages(self, setup: ToolSetup) -> tuple[str, ...]:
        """Return ("mypy",) when mypy is absent, empty tuple when already configured."""
        return ("mypy",) if not setup.configured else ()

    def plan_file_actions(self, setup: ToolSetup, ctx: ProvisionContext) -> list[FileAction]:
        """Write strict type-checking config when unconfigured; no gate step (mypy runs via ebpy check)."""
        if setup.configured:
            return []
        if ctx.has_pyproject:
            return [
                AppendText(
                    path="pyproject.toml",
                    content="\n" + MYPY_PYPROJECT_SECTION,
                    reason="type checking, strict — errors are ratcheted per file per rule, like Ruff's",
                )
            ]
        return [
            CreateFile(
                path="mypy.ini",
                content=MYPY_INI_CONTENT,
                reason="type checking, strict (no pyproject.toml to append to)",
            )
        ]
