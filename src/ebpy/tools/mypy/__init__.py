"""mypy analyzer and detector: execution, observation, and configuration detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...measurement import Failed, Measured, Observation, Unavailable
from ...models import Gap
from ...repo.detect.detector import MypySetup
from ...repo.detect.tooling import mypy_configured, mypy_strict_configured
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
