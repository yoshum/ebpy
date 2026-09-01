"""Detection contract for Increment D.

Each ToolDetector owns one question: is this tool configured, and how well?
Detection belongs here; the ratchet (Increment R) does not detect.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

from ebpy.models import ToolSetup

if TYPE_CHECKING:
    from ebpy.models import Gap, Language
    from ebpy.repo.facts import RepoFacts


S = TypeVar("S", bound=ToolSetup)


class ToolDetector(Protocol[S]):
    """Contract for a single-tool detector that backs the diagnosis command."""

    @property
    def name(self) -> str:
        """Unique short identifier for the tool (e.g. "mypy")."""
        ...

    @property
    def languages(self) -> frozenset[Language]:
        """The languages this detector's tool belongs to; empty means repository-wide."""
        ...

    @property
    def requires_repository_setup(self) -> bool:
        """Whether ebpy requires repository-side setup before proposing this tool for ratcheting.

        A statement of ebpy's policy, not of the tool's nature: ruff and mypy both run without
        a config file, so a name asserting they need one would be false. What is true is that
        ebpy waits for a repository to have adopted them — through bootstrap or a detected
        config — before proposing a ceiling. clippy has no adoption step to wait for.
        """
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
