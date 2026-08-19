"""The stable value seam between repository tools and ratchet decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Generic, Literal, TypeAlias, TypeVar

from .errors import ToolError
from .models import MYPY_COUNTER, AnalysisMeasurement
from .mypy_runner import MypyFailedError, MypyNotFoundError, run_mypy_check
from .ruff_runner import (
    RuffFailedError,
    RuffInvalidOutputError,
    RuffNotFoundError,
    run_ruff_check,
)

T = TypeVar("T")
FailureKind = Literal["execution-failed", "invalid-output"]

# A tool's own diagnostic block fits; a runaway trace is cut, and the marker says it was.
# A truncated detail that looked complete would be a report claiming more than it holds.
_DETAIL_LINES = 20
_DETAIL_CHARS = 4000
_TRUNCATION_MARK = "... (truncated)"


def _default_summary(observation: Unavailable | Failed) -> None:
    if not observation.summary:
        lines = observation.detail.splitlines()
        object.__setattr__(observation, "summary", lines[0] if lines else observation.detail)


@dataclass(frozen=True)
class Measured(Generic[T]):
    tool: str
    value: T


@dataclass(frozen=True)
class Unavailable:
    tool: str
    detail: str
    # One line for a sentence or a table row. Defaults to the detail's first line, which
    # is right when a tool said one thing; a runner that knows better passes its own.
    summary: str = ""

    def __post_init__(self) -> None:
        _default_summary(self)


@dataclass(frozen=True)
class Failed:
    tool: str
    failure_kind: FailureKind
    detail: str
    summary: str = ""

    def __post_init__(self) -> None:
        _default_summary(self)


Observation: TypeAlias = Measured[T] | Unavailable | Failed


@dataclass(frozen=True)
class Measurement:
    lint: Observation[AnalysisMeasurement]
    # Mapping, not dict: a frozen dataclass holding a mutable dict is frozen in name only,
    # and a measurement edited after the fact is no longer a record of what was measured.
    counters: Mapping[str, Observation[int]]

    def __post_init__(self) -> None:
        if MYPY_COUNTER not in self.counters:
            raise ValueError(f"Measurement requires an observation for {MYPY_COUNTER}")
        object.__setattr__(self, "counters", MappingProxyType(dict(self.counters)))


def _summary(error: BaseException) -> str:
    """The one line for a reader with room for one — a sentence, or a table row."""
    if isinstance(error, ToolError):
        return error.summary
    lines = str(error).splitlines()
    return lines[0] if lines else type(error).__name__


def _detail(error: BaseException) -> str:
    """Everything the tool said, bounded but not flattened.

    Cutting this down to one line here would lose it for every reader at once, while a
    reader that can only take one line can always take the summary. Two Ruff failures as
    different as a broken pyproject.toml and an unknown rule selector otherwise arrive
    as the same sentence.
    """
    text = (error.detail if isinstance(error, ToolError) else str(error)).strip()
    if not text:
        return type(error).__name__
    lines = text.splitlines()
    kept = "\n".join(lines[:_DETAIL_LINES])[:_DETAIL_CHARS].rstrip()
    return kept if kept == text else f"{kept}\n{_TRUNCATION_MARK}"


def _measure_lint(cwd: Path) -> Observation[AnalysisMeasurement]:
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


def _measure_mypy(cwd: Path) -> Observation[int]:
    try:
        return Measured(tool="mypy", value=run_mypy_check(cwd))
    except MypyNotFoundError as error:
        return Unavailable(tool="mypy", detail=_detail(error), summary=_summary(error))
    except (MypyFailedError, OSError) as error:
        return Failed(
            tool="mypy",
            failure_kind="execution-failed",
            detail=_detail(error),
            summary=_summary(error),
        )


def measure_repository(cwd: Path) -> Measurement:
    """Measure every independent capability, retaining partial success as data."""
    lint = _measure_lint(cwd)
    mypy = _measure_mypy(cwd)
    return Measurement(lint=lint, counters={MYPY_COUNTER: mypy})
