"""Record what happened, stamped with the current commit.

The only thing that writes the Work log in QUALITY.md — every other command
records counts, never why.
"""

from __future__ import annotations

from pathlib import Path

from ..git import head_commit
from ..models import LOG_KINDS, LogKind
from ..quality_file import write_quality_file
from ..state import append_log, empty_state, read_state, write_state

LOG_KIND_LIST = " | ".join(LOG_KINDS)


def is_log_kind(value: str) -> bool:
    return value in LOG_KINDS


def run_log(cwd: Path, kind: LogKind, text: str, rule: str | None) -> str:
    """`deferred` is the one that earns its keep: a refactor consciously not made,
    stamped with the commit it was seen at, so the next session can tell whether the
    observation still describes the code."""
    state = read_state(cwd) or empty_state()
    state = append_log(state, kind, text, head_commit(cwd), rule)
    write_state(cwd, state)
    write_quality_file(cwd, state)
    return f"Recorded {kind}: {text}"
