"""P0: read-only survey. ``--write`` persists QUALITY.md and the ledger."""

from __future__ import annotations

import json
from pathlib import Path

from ..decide.diagnose import diagnose
from ..errors import CommandError
from ..quality_file import write_quality_file
from ..render.report import render_diagnosis
from ..repo.facts import gather_facts
from ..repo.git import head_commit
from ..store.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..store.state import empty_state, with_diagnosis, write_state


def run_diagnose(cwd: Path, as_json: bool, write: bool) -> str:
    artifacts = read_ceiling_artifacts(cwd) if write else None
    if artifacts is not None and artifacts.kind == "invalid":
        raise CommandError(invalid_artifacts_message(artifacts))

    facts = gather_facts(cwd)
    diagnosis = diagnose(facts)

    if artifacts is not None:
        state = artifacts.ledger.state or empty_state()
        state = with_diagnosis(state, diagnosis, head_commit(cwd))
        write_state(cwd, state)
        write_quality_file(cwd, state)

    return json.dumps(diagnosis.to_dict(), indent=2) if as_json else render_diagnosis(diagnosis)
