"""The stable value seam between repository tools and ratchet decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Generic, Literal, TypeAlias, TypeVar

from ..cell_key import analyzer_of, is_analyzer_name
from ..errors import ToolError
from ..models import AnalysisMeasurement
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

T = TypeVar("T")
FailureKind = Literal["execution-failed", "invalid-output"]

# The shipped analyzers, sorted — not a registry. Adding a third means adding it here
# and teaching measure_repository to attempt it; nothing discovers analyzers dynamically.
ANALYZER_NAMES: tuple[str, ...] = ("mypy", "ruff")

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

# Whether an observation is usable as a verified ceiling. `None` stands for a ledger
# contract naming an analyzer this ebpy build has no runner for at all — that must fail
# closed rather than default to "unmeasured but fine", so it classifies as failed too.
AnalyzerStatus = Literal["complete", "incomplete", "unavailable", "failed"]


def classify(observation: Observation[AnalysisMeasurement] | None) -> AnalyzerStatus:
    if observation is None or isinstance(observation, Failed):
        return "failed"
    if isinstance(observation, Unavailable):
        return "unavailable"
    return "incomplete" if observation.value.unattributed else "complete"


@dataclass(frozen=True)
class Measurement:
    # Mapping, not dict: a frozen dataclass holding a mutable dict is frozen in name only,
    # and a measurement edited after the fact is no longer a record of what was measured.
    analyzers: Mapping[str, Observation[AnalysisMeasurement]]

    def __post_init__(self) -> None:
        for name, observation in self.analyzers.items():
            if not is_analyzer_name(name):
                raise ValueError(f"not a valid analyzer name: {name!r}")
            if observation.tool != name:
                raise ValueError(f"observation for {name!r} carries tool {observation.tool!r}, not {name!r}")
            if isinstance(observation, Measured):
                for rules in observation.value.cells.values():
                    for rule in rules:
                        if analyzer_of(rule) != name:
                            raise ValueError(f"rule {rule!r} does not belong to analyzer {name!r}")
        # AnalysisMeasurement.__post_init__ already deep-froze each cell mapping; only
        # the outer analyzer -> observation mapping still needs freezing here.
        object.__setattr__(self, "analyzers", MappingProxyType(dict(self.analyzers)))


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


def measure_repository(cwd: Path) -> Measurement:
    """Measure every independent capability, retaining partial success as data."""
    ruff = _measure_ruff(cwd)
    mypy = _measure_mypy(cwd)
    return Measurement(analyzers={"ruff": ruff, "mypy": mypy})
