"""Measurement value types — a leaf module with no dependency on the measurement registry.

Keeping these types in a separate module lets future tool-specific analyzer modules import
Observation, Measured, etc. without creating a circular dependency with the registry that
will import those analyzer modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Generic, Literal, TypeAlias, TypeVar

from ..cell_key import analyzer_of, is_analyzer_name
from ..errors import ToolError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ..models import AnalysisMeasurement

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
    """A tool ran and produced a usable value — the one observation a ceiling can be built on."""

    tool: str
    value: T


@dataclass(frozen=True)
class Unavailable:
    """A tool could not run at all (not installed, not configured) — nothing to measure."""

    tool: str
    detail: str
    # One line for a sentence or a table row. Defaults to the detail's first line, which
    # is right when a tool said one thing; a runner that knows better passes its own.
    summary: str = ""

    def __post_init__(self) -> None:
        """Fall back to the detail's first line when the runner supplied no summary."""
        _default_summary(self)

    @classmethod
    def from_tool_error(cls, tool: str, error: BaseException) -> Unavailable:
        """Build an Unavailable from a tool error, capturing its detail and summary readings."""
        return cls(tool=tool, detail=_describe(error), summary=_summarize(error))


@dataclass(frozen=True)
class Failed:
    """A tool ran but did not yield a measurement — it errored or produced output ebpy cannot read."""

    tool: str
    failure_kind: FailureKind
    detail: str
    summary: str = ""

    def __post_init__(self) -> None:
        """Fall back to the detail's first line when the runner supplied no summary."""
        _default_summary(self)

    @classmethod
    def from_tool_error(cls, tool: str, failure_kind: FailureKind, error: BaseException) -> Failed:
        """Build a Failed from a tool error, capturing its detail and summary readings."""
        return cls(
            tool=tool,
            failure_kind=failure_kind,
            detail=_describe(error),
            summary=_summarize(error),
        )


Observation: TypeAlias = Measured[T] | Unavailable | Failed

# Whether an observation is usable as a verified ceiling. "no-runner" stands for a ledger
# contract naming an analyzer this ebpy build has no runner for at all: `None` rather than
# any observation shape. It is not folded into "failed" so that callers can word the one
# unfixable case — reach for a build that ships the runner — apart from a tool that broke.
AnalyzerStatus = Literal["complete", "incomplete", "unavailable", "failed", "no-runner"]


def classify(observation: Observation[AnalysisMeasurement] | None) -> AnalyzerStatus:
    """Reduce an observation (or its absence) to the status a caller reasons about."""
    if observation is None:
        return "no-runner"
    if isinstance(observation, Failed):
        return "failed"
    if isinstance(observation, Unavailable):
        return "unavailable"
    return "incomplete" if observation.value.unattributed else "complete"


@dataclass(frozen=True)
class Measurement:
    """One observation per analyzer, validated and frozen — the whole of what a run measured."""

    # Mapping, not dict: a frozen dataclass holding a mutable dict is frozen in name only,
    # and a measurement edited after the fact is no longer a record of what was measured.
    analyzers: Mapping[str, Observation[AnalysisMeasurement]]

    def __post_init__(self) -> None:
        """Reject an analyzer name, tool, or rule that does not belong, then freeze the mapping."""
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


def _summarize(error: BaseException) -> str:
    """Return the one line for a reader with room for one — a sentence, or a table row."""
    if isinstance(error, ToolError):
        return error.summary
    lines = str(error).splitlines()
    return lines[0] if lines else type(error).__name__


def _describe(error: BaseException) -> str:
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
