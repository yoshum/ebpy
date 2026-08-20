"""The list an unattended run works down, top to bottom.

Derived from state rather than stored, so it cannot drift from the numbers
beside it — and so a session that picks the file up cold knows where it is
without reading the log.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import State
from ..persist.state import total_violations

_NEXT_RULES_SHOWN = 5


@dataclass(frozen=True)
class WorklistItem:
    done: bool
    label: str
    detail: str = ""
    children: tuple[str, ...] = field(default=())


def _open_bootstrap_gaps(state: State) -> int:
    gaps = state.diagnosis.gaps if state.diagnosis else ()
    return sum(1 for gap in gaps if gap.phase == "bootstrap")


def _smallest_backlogs(state: State) -> tuple[str, ...]:
    draining = sorted(
        ((name, rule.current) for name, rule in state.rules.items() if rule.current > 0),
        key=lambda item: (item[1], item[0]),
    )
    return tuple(f"`{name}` — {current} left" for name, current in draining[:_NEXT_RULES_SHOWN])


def build_worklist(state: State) -> list[WorklistItem]:
    bootstrap_gaps = _open_bootstrap_gaps(state)
    backlog = total_violations(state)
    rule_count = sum(1 for rule in state.rules.values() if rule.current > 0)
    return [
        WorklistItem(
            done=state.diagnosed_at is not None,
            label="P0 diagnose",
            detail=f"taken {state.diagnosed_at}" if state.diagnosed_at else "not yet run",
        ),
        WorklistItem(
            done=state.diagnosed_at is not None and bootstrap_gaps == 0,
            label="P1 bootstrap",
            detail="nothing missing" if bootstrap_gaps == 0 else f"{bootstrap_gaps} gap(s) still open",
        ),
        WorklistItem(
            done=state.frozen_at is not None,
            label="P2 freeze",
            detail=f"frozen {state.frozen_at}" if state.frozen_at else "baseline not pinned yet",
        ),
        WorklistItem(
            done=state.frozen_at is not None and backlog == 0,
            label="P3 drain",
            detail="backlog empty" if backlog == 0 else f"{backlog} violations across {rule_count} rules",
            children=_smallest_backlogs(state),
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
