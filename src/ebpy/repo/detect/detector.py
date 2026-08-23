"""Detection contract for Increment D.

Each ToolDetector owns one question: is this tool configured, and how well?
Detection belongs here; the ratchet (Increment R) does not detect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from ...models import Gap
    from ..facts import RepoFacts


@dataclass(frozen=True)
class ToolSetup:
    """Baseline detection result shared by every tool."""

    configured: bool


@dataclass(frozen=True)
class MypySetup(ToolSetup):
    """Detection result for mypy, extending ToolSetup with strictness."""

    strict: bool  # strict=False surfaces as a tighten gap


S = TypeVar("S", bound=ToolSetup)


class ToolDetector(Protocol[S]):
    """Contract for a single-tool detector that backs the diagnosis command."""

    @property
    def name(self) -> str:
        """Unique short identifier for the tool (e.g. "mypy")."""
        ...

    def detect(self, facts: RepoFacts) -> S:
        """Inspect repo facts and return the tool's setup state."""
        ...

    def gaps(self, setup: S) -> list[Gap]:
        """Return actionable gaps for the given setup (empty when fully configured)."""
        ...

    def render_row(self, setup: S) -> str:
        """Render a one-line summary row for the diagnosis table."""
        ...
