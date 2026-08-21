"""The list an unattended run works down, top to bottom.

Presents the verdict from `decide/worklist.py` as a checklist — the box, the
label, and the prose beside each phase — so a session that picks the file up
cold knows where it is without reading the log.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..decide.worklist import WorklistVerdict


@dataclass(frozen=True)
class WorklistItem:
    done: bool
    label: str
    detail: str = ""
    children: tuple[str, ...] = field(default=())


def _backlog_children(smallest_backlogs: tuple[tuple[str, int], ...]) -> tuple[str, ...]:
    return tuple(f"`{name}` — {current} left" for name, current in smallest_backlogs)


def build_worklist(verdict: WorklistVerdict) -> list[WorklistItem]:
    return [
        WorklistItem(
            done=verdict.diagnosed,
            label="P0 diagnose",
            detail=f"taken {verdict.diagnosed_at}" if verdict.diagnosed_at else "not yet run",
        ),
        WorklistItem(
            done=verdict.bootstrap_done,
            label="P1 bootstrap",
            detail="nothing missing"
            if verdict.bootstrap_gaps == 0
            else f"{verdict.bootstrap_gaps} gap(s) still open",
        ),
        WorklistItem(
            done=verdict.frozen,
            label="P2 freeze",
            detail=f"frozen {verdict.frozen_at}" if verdict.frozen_at else "baseline not pinned yet",
        ),
        WorklistItem(
            done=verdict.drained,
            label="P3 drain",
            detail="backlog empty"
            if verdict.backlog == 0
            else f"{verdict.backlog} findings across {verdict.rule_count} rules",
            children=_backlog_children(verdict.smallest_backlogs),
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
