"""The stable value seam between repository tools and ratchet decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
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


@dataclass(frozen=True)
class Unavailable:
    tool: str
    detail: str


@dataclass(frozen=True)
class Failed:
    tool: str
    failure_kind: FailureKind
    detail: str


Observation: TypeAlias = Measured[T] | Unavailable | Failed


@dataclass(frozen=True)
class Measurement:
    lint: Observation[LintMeasurement]
    # Mapping, not dict: a frozen dataclass holding a mutable dict is frozen in name only,
    # and a measurement edited after the fact is no longer a record of what was measured.
    counters: Mapping[str, Observation[int]]

    def __post_init__(self) -> None:
        if MYPY_COUNTER not in self.counters:
            raise ValueError(f"Measurement requires an observation for {MYPY_COUNTER}")
        object.__setattr__(self, "counters", MappingProxyType(dict(self.counters)))


def _detail(error: BaseException) -> str:
    """One line, because that is what a report line and a sentence can carry.

    Runners must therefore put the reason on the first line; anything below it is lost
    here rather than at the point somebody would notice.
    """
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
