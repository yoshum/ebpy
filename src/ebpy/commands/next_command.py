"""What to drain first, and what each fix enforces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..baseline import read_suppressions
from ..ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ..drain_order import build_drain_plan
from ..facts import list_source_paths, read_sources
from ..fan_in import build_graph, count_importers, importers_of
from ..models import Suppression
from ..render.next import render_next


@dataclass(frozen=True)
class NextResult:
    ok: bool
    message: str


def _gather_importers(cwd: Path, entries: list[Suppression]) -> dict[str, int]:
    sources = read_sources(cwd, list_source_paths(cwd))
    return importers_of(count_importers(build_graph(sources)), [entry.file for entry in entries])


def run_next(cwd: Path, as_json: bool, fan_in: bool) -> NextResult:
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        return NextResult(ok=False, message=invalid_artifacts_message(artifacts))
    entries = read_suppressions(cwd)
    # Reading every source file to parse its imports is the weight of a whole-repo pass,
    # not of a command you run between edits — so it is a flag rather than the default.
    importers = _gather_importers(cwd, entries) if fan_in else {}
    plan = build_drain_plan(entries, importers)
    message = json.dumps(plan.to_dict(), indent=2) if as_json else render_next(plan)
    return NextResult(ok=True, message=message)
