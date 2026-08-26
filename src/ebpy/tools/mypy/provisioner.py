"""mypy provisioner: installs the package and writes strict type-checking config."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ebpy.decide.provisioner import AppendText, CreateFile, WithheldConfig

from .config import MYPY_INI_CONTENT, MYPY_PYPROJECT_SECTION

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
        """Write strict type-checking config when unconfigured, withhold it when configured.

        No gate step either way: mypy runs through `ebpy check`. A repository that already
        configures mypy is shown the config rather than having it written over.
        """
        if ctx.has_pyproject:
            path, content = "pyproject.toml", "\n" + MYPY_PYPROJECT_SECTION
            reason = "type checking, strict — errors are ratcheted per file per rule, like Ruff's"
        else:
            path, content = "mypy.ini", MYPY_INI_CONTENT
            reason = "type checking, strict (no pyproject.toml to append to)"

        if setup.configured:
            return [WithheldConfig(path, content, reason, note="mypy is already configured")]
        if ctx.has_pyproject:
            return [AppendText(path=path, content=content, reason=reason)]
        return [CreateFile(path=path, content=content, reason=reason)]
