"""The list an unattended run works down, top to bottom.

Presents the verdict from `decide/worklist.py` as a checklist — the box, the
label, and the prose beside each phase — so a session that picks the file up
cold knows where it is without reading the log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ebpy.decide.worklist import Worklist


@dataclass(frozen=True)
class WorklistItem:
    """One line of the worklist: whether it is done, its label, detail, and any child lines."""

    done: bool
    label: str
    detail: str = ""
    children: tuple[str, ...] = field(default=())


def _backlog_children(smallest_backlogs: tuple[tuple[str, int], ...]) -> tuple[str, ...]:
    return tuple(f"`{name}` — {current} left" for name, current in smallest_backlogs)


def build_worklist_items(worklist: Worklist) -> list[WorklistItem]:
    return [
        WorklistItem(
            done=worklist.diagnosed,
            label="P0 diagnose",
            detail=f"taken {worklist.diagnosed_at}" if worklist.diagnosed_at else "not yet run",
        ),
        WorklistItem(
            done=worklist.bootstrap_done,
            label="P1 bootstrap",
            detail="nothing missing"
            if worklist.bootstrap_gaps == 0
            else f"{worklist.bootstrap_gaps} gap(s) still open",
        ),
        WorklistItem(
            done=worklist.frozen,
            label="P2 freeze",
            detail=f"frozen {worklist.frozen_at}" if worklist.frozen_at else "baseline not pinned yet",
        ),
        WorklistItem(
            done=worklist.drained,
            label="P3 drain",
            detail="backlog empty"
            if worklist.backlog == 0
            else f"{worklist.backlog} findings across {worklist.rule_count} rules",
            children=_backlog_children(worklist.smallest_backlogs),
        ),
        WorklistItem(
            done=False,
            label="P4 tighten",
            detail="add the next rule tier, then freeze and drain again",
        ),
        WorklistItem(
            done=False,
            label="P5 duplication and dead code",
            detail="report-only scans; extraction is judgment, not a threshold",
        ),
    ]


def render_worklist(items: list[WorklistItem]) -> list[str]:
    lines: list[str] = []
    for item in items:
        box = "[x]" if item.done else "[ ]"
        suffix = f" — {item.detail}" if item.detail else ""
        lines.append(f"- {box} **{item.label}**{suffix}")
        lines.extend(f"  - [ ] {child}" for child in item.children)
    return lines
