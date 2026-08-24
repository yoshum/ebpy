"""P0: read-only survey. ``--write`` persists QUALITY.md and the ledger."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ebpy.decide.diagnose import diagnose
from ebpy.errors import CommandError
from ebpy.quality_file import write_quality_file
from ebpy.render.report import render_diagnosis
from ebpy.repo.facts import gather_facts
from ebpy.repo.git import head_commit
from ebpy.store.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ebpy.store.state import empty_state, with_diagnosis, write_state

if TYPE_CHECKING:
    from pathlib import Path


def run_diagnose(cwd: Path, as_json: bool, write: bool) -> str:
    """Run ``ebpy diagnose``: measure the repository and, when writing, record the diagnosis in the ledger."""
    artifacts = read_ceiling_artifacts(cwd) if write else None
    if artifacts is not None and artifacts.kind == "invalid":
        raise CommandError(invalid_artifacts_message(artifacts))

    existing = artifacts.ledger.state if artifacts is not None else None
    frozen_analyzers = existing.frozen_analyzers if existing is not None else ()

    facts = gather_facts(cwd)
    diagnosis = diagnose(facts, frozen_analyzers)

    if artifacts is not None:
        state = existing or empty_state()
        state = with_diagnosis(state, diagnosis, head_commit(cwd))
        write_state(cwd, state)
        write_quality_file(cwd, state)

    return json.dumps(diagnosis.to_dict(), indent=2) if as_json else render_diagnosis(diagnosis)
