"""P0: read-only survey. ``--write`` persists QUALITY.md and the ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..diagnose import diagnose
from ..facts import gather_facts
from ..git import head_commit
from ..quality_file import write_quality_file
from ..render.report import render_diagnosis
from ..state import empty_state, with_diagnosis, write_state


@dataclass(frozen=True)
class DiagnoseResult:
    ok: bool
    message: str


def run_diagnose(cwd: Path, as_json: bool, write: bool) -> DiagnoseResult:
    artifacts = read_ceiling_artifacts(cwd) if write else None
    if artifacts is not None and artifacts.kind == "invalid":
        return DiagnoseResult(ok=False, message=invalid_artifacts_message(artifacts))

    facts = gather_facts(cwd)
    diagnosis = diagnose(facts)

    if artifacts is not None:
        state = artifacts.ledger.state or empty_state()
        state = with_diagnosis(state, diagnosis, head_commit(cwd))
        write_state(cwd, state)
        write_quality_file(cwd, state)

    message = json.dumps(diagnosis.to_dict(), indent=2) if as_json else render_diagnosis(diagnosis)
    return DiagnoseResult(ok=True, message=message)
