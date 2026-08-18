"""The stable value seam between repository tools and ratchet decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Literal, TypeAlias, TypeVar

from .models import MYPY_COUNTER, LintMeasurement
from .mypy_runner import MypyFailedError, MypyNotFoundError, run_mypy_check
from .ruff_runner import (
    RuffFailedError,
    RuffInvalidOutputError,
    RuffNotFoundError,
    run_ruff_check,
)

T = TypeVar("T")
FailureKind = Literal["execution-failed", "invalid-output"]


@dataclass(frozen=True)
class Measured(Generic[T]):
    tool: str
    value: T
    version: str | None = None


@dataclass(frozen=True)
class Unavailable:
    tool: str
    detail: str


@dataclass(frozen=True)
class Failed:
    tool: str
    failure_kind: FailureKind
    detail: str
    version: str | None = None


Observation: TypeAlias = Measured[T] | Unavailable | Failed


@dataclass(frozen=True)
class Measurement:
    lint: Observation[LintMeasurement]
    counters: dict[str, Observation[int]] = field(default_factory=dict)


def _detail(error: BaseException) -> str:
    lines = str(error).splitlines()
    return lines[0] if lines else type(error).__name__


def _measure_lint(cwd: Path) -> Observation[LintMeasurement]:
    try:
        return Measured(tool="ruff", value=run_ruff_check(cwd))
    except RuffNotFoundError as error:
        return Unavailable(tool="ruff", detail=_detail(error))
    except RuffInvalidOutputError as error:
        return Failed(tool="ruff", failure_kind="invalid-output", detail=_detail(error))
    except (RuffFailedError, OSError) as error:
        return Failed(tool="ruff", failure_kind="execution-failed", detail=_detail(error))


def _measure_mypy(cwd: Path) -> Observation[int]:
    try:
        return Measured(tool="mypy", value=run_mypy_check(cwd))
    except MypyNotFoundError as error:
        return Unavailable(tool="mypy", detail=_detail(error))
    except (MypyFailedError, OSError) as error:
        return Failed(tool="mypy", failure_kind="execution-failed", detail=_detail(error))


def measure_repository(cwd: Path) -> Measurement:
    """Measure every independent capability, retaining partial success as data."""
    lint = _measure_lint(cwd)
    mypy = _measure_mypy(cwd)
    return Measurement(lint=lint, counters={MYPY_COUNTER: mypy})
