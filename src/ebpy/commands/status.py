"""The current phase, the backlog, and the smallest remaining counts."""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import CommandError
from ..persist.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..persist.state import find_regressions, improvements, state_to_dict, total_violations
from ..quality_file import freshness_of

_NEXT_RULE_SAMPLE = 5


def run_status(cwd: Path, as_json: bool) -> str:
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        raise CommandError(invalid_artifacts_message(artifacts))
    state = artifacts.ledger.state
    if not state:
        return "No .ebpy/state.json here. Start with `ebpy diagnose`."
    if as_json:
        return json.dumps(state_to_dict(state), indent=2)

    freshness = freshness_of(cwd, state)
    draining = sorted(
        ((name, rule.current) for name, rule in state.rules.items() if rule.current > 0),
        key=lambda item: (item[1], item[0]),
    )[:_NEXT_RULE_SAMPLE]

    return "\n".join(
        [
            *([f"STALE      {freshness.reason}", ""] if freshness.stale else []),
            f"phase      {state.phase}",
            f"frozen     {state.frozen_at or 'never'}",
            f"backlog    {total_violations(state)}",
            f"improved   {len(improvements(state))} rules",
            f"regressed  {len(find_regressions(state))} rules",
            "",
            "smallest remaining backlogs:" if draining else "backlog is empty.",
            *(f"  {current}  {name}" for name, current in draining),
            *(
                ["", "`ebpy next` ranks these by what they cost and what each one enforces."]
                if draining
                else []
            ),
            "",
        ]
    )
