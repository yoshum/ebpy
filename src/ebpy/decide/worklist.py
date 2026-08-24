"""Where an unattended run stands on each phase, decided from state.

The worklist an agent works down is derived from the ledger rather than stored,
so it cannot drift from the numbers beside it. This decides the facts each phase
rests on — whether it is done, and the counts and names that justify that — and
leaves the prose that presents them to `render/worklist.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from operator import itemgetter
from typing import TYPE_CHECKING

from ebpy.store.state import total_violations

if TYPE_CHECKING:
    from ebpy.models import State

# How many of the smallest remaining backlogs the drain phase names as next targets.
NEXT_RULES_SHOWN = 5


@dataclass(frozen=True)
class Worklist:
    """Whether each phase is done, and the facts that verdict rests on.

    A phase is only done once the phase before it is: bootstrap needs a diagnosis, and
    the backlog is not "drained" until there is a frozen ceiling to have drained it below.
    `smallest_backlogs` ranks the draining rules with the fewest violations left first, as
    (rule, current) pairs, capped at `NEXT_RULES_SHOWN`.
    """

    diagnosed: bool
    diagnosed_at: str | None
    bootstrap_done: bool
    bootstrap_gaps: int
    frozen: bool
    frozen_at: str | None
    drained: bool
    backlog: int
    rule_count: int
    smallest_backlogs: tuple[tuple[str, int], ...]


def _open_bootstrap_gaps(state: State) -> int:
    gaps = state.diagnosis.gaps if state.diagnosis else ()
    return sum(1 for gap in gaps if gap.phase == "bootstrap")


def _smallest_backlogs(state: State) -> tuple[tuple[str, int], ...]:
    draining = sorted(
        ((name, rule.current) for name, rule in state.rules.items() if rule.current > 0),
        key=itemgetter(1, 0),
    )
    return tuple(draining[:NEXT_RULES_SHOWN])


def build_worklist(state: State) -> Worklist:
    """Derive from the ledger which phase the user is in and what step comes next."""
    diagnosed = state.diagnosed_at is not None
    bootstrap_gaps = _open_bootstrap_gaps(state)
    frozen = state.frozen_at is not None
    backlog = total_violations(state)
    return Worklist(
        diagnosed=diagnosed,
        diagnosed_at=state.diagnosed_at,
        bootstrap_done=diagnosed and bootstrap_gaps == 0,
        bootstrap_gaps=bootstrap_gaps,
        frozen=frozen,
        frozen_at=state.frozen_at,
        drained=frozen and backlog == 0,
        backlog=backlog,
        rule_count=sum(1 for rule in state.rules.values() if rule.current > 0),
        smallest_backlogs=_smallest_backlogs(state),
    )
