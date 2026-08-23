"""The stable value seam between repository tools and ratchet decisions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ..models import AnalysisMeasurement, ToolingPresence
from ._mypy import (
    MypyFailedError,
    MypyInvalidOutputError,
    MypyNotFoundError,
    run_mypy_check,
)
from ._ruff import (
    RuffFailedError,
    RuffInvalidOutputError,
    RuffNotFoundError,
    run_ruff_check,
)
from ._values import (
    _DETAIL_LINES as _DETAIL_LINES,
)
from ._values import (
    AnalyzerStatus,
    Failed,
    FailureKind,
    Measured,
    Measurement,
    Observation,
    Unavailable,
    _detail,
    _summary,
    classify,
)

__all__ = [
    "AnalyzerStatus",
    "Failed",
    "FailureKind",
    "Measured",
    "Measurement",
    "Observation",
    "Unavailable",
    "classify",
]


def _measure_ruff(cwd: Path) -> Observation[AnalysisMeasurement]:
    try:
        return Measured(tool="ruff", value=run_ruff_check(cwd))
    except RuffNotFoundError as error:
        return Unavailable(tool="ruff", detail=_detail(error), summary=_summary(error))
    except RuffInvalidOutputError as error:
        return Failed(
            tool="ruff",
            failure_kind="invalid-output",
            detail=_detail(error),
            summary=_summary(error),
        )
    except (RuffFailedError, OSError) as error:
        return Failed(
            tool="ruff",
            failure_kind="execution-failed",
            detail=_detail(error),
            summary=_summary(error),
        )


def _measure_mypy(cwd: Path) -> Observation[AnalysisMeasurement]:
    try:
        return Measured(tool="mypy", value=run_mypy_check(cwd))
    except MypyNotFoundError as error:
        return Unavailable(tool="mypy", detail=_detail(error), summary=_summary(error))
    # MypyInvalidOutputError subclasses MypyFailedError, so it must be caught first —
    # otherwise every invalid-output failure would be misreported as execution-failed.
    except MypyInvalidOutputError as error:
        return Failed(
            tool="mypy",
            failure_kind="invalid-output",
            detail=_detail(error),
            summary=_summary(error),
        )
    except (MypyFailedError, OSError) as error:
        return Failed(
            tool="mypy",
            failure_kind="execution-failed",
            detail=_detail(error),
            summary=_summary(error),
        )


@dataclass(frozen=True)
class AnalyzerSpec:
    """Everything ebpy knows how to do with one analyzer, in one place.

    Adding a third analyzer is one entry in `ANALYZER_SPECS`: `measure` turns a repository
    into an observation, `configured` reads whether the repository set the tool up (for the
    unratcheted note), and `noun` is what that note calls the tool's findings. measurement,
    check, and quality all read this registry, so the wiring cannot desync between them.
    """

    name: str
    measure: Callable[[Path], Observation[AnalysisMeasurement]]
    configured: Callable[[ToolingPresence], bool]
    noun: str


# The shipped analyzers. Everything analyzer-specific is here; nothing discovers analyzers
# dynamically. `configured` is a literal field access, not getattr(tooling, name): a typo
# is then a mypy error rather than a silently-always-false lookup.
ANALYZER_SPECS: tuple[AnalyzerSpec, ...] = (
    AnalyzerSpec(
        name="ruff",
        measure=_measure_ruff,
        configured=lambda tooling: tooling.ruff,
        noun="Lint violations",
    ),
    AnalyzerSpec(
        name="mypy",
        measure=_measure_mypy,
        configured=lambda tooling: tooling.mypy,
        noun="Type errors",
    ),
)

ANALYZER_SPECS_BY_NAME: Mapping[str, AnalyzerSpec] = MappingProxyType(
    {spec.name: spec for spec in ANALYZER_SPECS}
)

# The shipped analyzers' names, sorted. Derived from the registry so it cannot drift from it.
ANALYZER_NAMES: tuple[str, ...] = tuple(sorted(ANALYZER_SPECS_BY_NAME))


def measure_repository(cwd: Path) -> Measurement:
    """Measure every independent capability, retaining partial success as data."""
    return Measurement(analyzers={spec.name: spec.measure(cwd) for spec in ANALYZER_SPECS})
