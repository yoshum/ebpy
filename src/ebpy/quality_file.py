"""Re-renders QUALITY.md from state, carrying the owner's notes block across untouched."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .decide.freshness import Freshness, FreshnessInput, assess_freshness
from .render.quality import QUALITY_FILE, extract_notes, render_quality
from .repo.git import commits_since, head_commit

if TYPE_CHECKING:
    from pathlib import Path

    from .models import State


def freshness_of(cwd: Path, state: State) -> Freshness:
    head = head_commit(cwd)
    return assess_freshness(
        FreshnessInput(
            diagnosed_at=state.diagnosed_at,
            diagnosed_commit=state.diagnosed_commit,
            head_commit=head,
            commits_since=commits_since(cwd, state.diagnosed_commit),
            now=datetime.now(UTC),
        )
    )


def write_quality_file(cwd: Path, state: State) -> Path:
    path = cwd / QUALITY_FILE
    try:
        existing: str | None = path.read_text(encoding="utf-8")
    except OSError:
        existing = None
    notes = extract_notes(existing)
    path.write_text(render_quality(state, notes, freshness_of(cwd, state)), encoding="utf-8")
    return path
