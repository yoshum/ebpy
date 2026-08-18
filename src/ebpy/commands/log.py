"""Record what happened, stamped with the current commit.

The only thing that writes the Work log in QUALITY.md — every other command
records counts, never why.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..git import head_commit
from ..models import LOG_KINDS, LogKind
from ..quality_file import write_quality_file
from ..state import append_log, empty_state, write_state

LOG_KIND_LIST = " | ".join(LOG_KINDS)


@dataclass(frozen=True)
class LogResult:
    ok: bool
    message: str


def is_log_kind(value: str) -> bool:
    return value in LOG_KINDS


def run_log(cwd: Path, kind: LogKind, text: str, rule: str | None) -> LogResult:
    """`deferred` is the one that earns its keep: a refactor consciously not made,
    stamped with the commit it was seen at, so the next session can tell whether the
    observation still describes the code."""
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        return LogResult(ok=False, message=invalid_artifacts_message(artifacts))
    state = artifacts.ledger.state or empty_state()
    state = append_log(state, kind, text, head_commit(cwd), rule)
    write_state(cwd, state)
    write_quality_file(cwd, state)
    return LogResult(ok=True, message=f"Recorded {kind}: {text}")
