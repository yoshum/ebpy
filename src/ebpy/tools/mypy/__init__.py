"""mypy analyzer and detector: execution, observation, and configuration detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...decide.provisioner import FileAction
from ...generate.configs import MYPY_INI_CONTENT, MYPY_PYPROJECT_SECTION
from ...measurement import Failed, Measured, Observation, Unavailable
from ...models import Gap, ToolSetup
from ...repo.detect.tooling import _ini_has_section, _tool_table
from ._runner import (
    MypyFailedError,
    MypyInvalidOutputError,
    MypyNotFoundError,
    run_mypy_check,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ...models import AnalysisMeasurement
    from ...repo.facts import RepoFacts


def mypy_configured(
    root_entries: tuple[str, ...],
    pyproject: dict[str, Any] | None,
    configs: dict[str, str],
) -> bool:
    """Return True if any mypy configuration is present in standard locations."""
    return (
        _tool_table(pyproject, "mypy") is not None
        or "mypy.ini" in root_entries
        or ".mypy.ini" in root_entries
        or _ini_has_section(configs.get("setup.cfg"), "mypy")
    )


def mypy_strict_configured(pyproject: dict[str, Any] | None, configs: dict[str, str]) -> bool:
    """Return True when mypy's strict mode is enabled in pyproject or an ini config."""
    table = _tool_table(pyproject, "mypy")
    if table is not None and table.get("strict") is True:
        return True
    for name in ("mypy.ini", ".mypy.ini", "setup.cfg"):
        text = configs.get(name)
        if text and re.search(r"^\s*strict\s*=\s*[Tt]rue", text, re.MULTILINE):
            return True
    return False


@dataclass(frozen=True)
class MypySetup(ToolSetup):
    """Detection result for mypy, extending ToolSetup with strictness."""

    strict: bool  # strict=False surfaces as a tighten gap

    def to_dict(self) -> dict[str, Any]:
        """Serialize configured plus mypy's strictness to the stored JSON shape."""
        return {**super().to_dict(), "strict": self.strict}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> MypySetup:
        """Reconstruct a mypy setup, reading back its strictness alongside configured."""
        return cls(configured=bool(raw.get("configured")), strict=bool(raw.get("strict")))


@dataclass(frozen=True)
class MypyDetector:
    """Detects whether mypy is configured (and whether strict mode is on) and reports any gaps."""

    @property
    def name(self) -> str:
        """Unique short identifier for mypy."""
        return "mypy"

    def detect(self, facts: RepoFacts) -> MypySetup:
        """Return configured and strict state based on mypy config found in the repository."""
        return MypySetup(
            configured=mypy_configured(facts.root_entries, facts.pyproject, facts.extra_config_text),
            strict=mypy_strict_configured(facts.pyproject, facts.extra_config_text),
        )

    def gaps(self, setup: MypySetup) -> list[Gap]:
        """Return a bootstrap gap when mypy is absent, a tighten gap when strict is off, empty otherwise."""
        if not setup.configured:
            return [
                Gap(
                    id="mypy",
                    title="No type checking",
                    detail="Type hints are the cheapest rule set there is. mypy errors are "
                    "grandfathered per file per rule, one `mypy:<code>` cell at a time, exactly as "
                    "Ruff findings are.",
                    phase="bootstrap",
                )
            ]
        if not setup.strict:
            return [
                Gap(
                    id="mypy-strict",
                    title="mypy `strict` is off",
                    detail="Everything else in the type tier is moot until this is on. Enable it and "
                    "let the per-cell ratchet hold the line while the backlog drains.",
                    phase="tighten",
                )
            ]
        return []

    def render_row(self, setup: MypySetup) -> str:
        """Render a one-line mypy row for the diagnosis table."""
        state = "strict" if setup.strict else ("yes (not strict)" if setup.configured else "no")
        return f"  mypy              {state}"


@dataclass(frozen=True)
class MypyProvisioner:
    """Provisioner for mypy: installs the package and writes strict type-checking config."""

    @property
    def name(self) -> str:
        """Unique short identifier for mypy."""
        return "mypy"

    def packages(self, setup: ToolSetup) -> tuple[str, ...]:
        """Return ("mypy",) when mypy is absent, empty tuple when already configured."""
        return ("mypy",) if not setup.configured else ()

    def config_actions(self, setup: ToolSetup, has_pyproject: bool, target_version: str) -> list[FileAction]:  # noqa: ARG002
        """Append a [tool.mypy] section to pyproject.toml, or create mypy.ini when there is no pyproject."""
        if setup.configured:
            return []
        if has_pyproject:
            return [
                FileAction(
                    path="pyproject.toml",
                    content="\n" + MYPY_PYPROJECT_SECTION,
                    mode="append",
                    reason="type checking, strict — errors are ratcheted per file per rule, like Ruff's",
                )
            ]
        return [
            FileAction(
                path="mypy.ini",
                content=MYPY_INI_CONTENT,
                mode="create",
                reason="type checking, strict (no pyproject.toml to append to)",
            )
        ]

    def workflow_steps(self, _run_prefix: str) -> list[str]:
        """Return empty list: type checking runs through ebpy check, not a raw mypy CI step."""
        return []


@dataclass(frozen=True)
class MypyAnalyzer:
    """mypy analyzer that owns the full observation-building try/except."""

    name: str = "mypy"
    noun: str = "Type errors"

    def measure(self, cwd: Path) -> Observation[AnalysisMeasurement]:
        """Run mypy against the repository at cwd and return the observation."""
        try:
            return Measured(tool="mypy", value=run_mypy_check(cwd))
        except MypyNotFoundError as error:
            return Unavailable.from_tool_error("mypy", error)
        # MypyInvalidOutputError subclasses MypyFailedError, so it must be caught first —
        # otherwise every invalid-output failure would be misreported as execution-failed.
        except MypyInvalidOutputError as error:
            return Failed.from_tool_error("mypy", "invalid-output", error)
        except (MypyFailedError, OSError) as error:
            return Failed.from_tool_error("mypy", "execution-failed", error)
