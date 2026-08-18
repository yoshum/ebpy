"""P0: read-only survey. ``--write`` persists QUALITY.md and the ledger."""

from __future__ import annotations

import json
from pathlib import Path

from ..diagnose import diagnose
from ..facts import gather_facts
from ..git import head_commit
from ..quality_file import write_quality_file
from ..render.report import render_diagnosis
from ..state import empty_state, read_state, with_diagnosis, write_state


def run_diagnose(cwd: Path, as_json: bool, write: bool) -> str:
    facts = gather_facts(cwd)
    diagnosis = diagnose(facts)

    if write:
        state = read_state(cwd) or empty_state()
        state = with_diagnosis(state, diagnosis, head_commit(cwd))
        write_state(cwd, state)
        write_quality_file(cwd, state)

    return json.dumps(diagnosis.to_dict(), indent=2) if as_json else render_diagnosis(diagnosis)
