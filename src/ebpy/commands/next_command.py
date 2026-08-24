"""What to drain first, and what each fix enforces."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ebpy.decide.drain_order import build_drain_plan
from ebpy.errors import CommandError
from ebpy.models import Suppression
from ebpy.render.next import render_next
from ebpy.repo.facts import list_source_paths, read_sources
from ebpy.repo.fan_in import build_graph, count_importers, importers_of
from ebpy.store.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts

if TYPE_CHECKING:
    from pathlib import Path


def _gather_importers(cwd: Path, entries: list[Suppression]) -> dict[str, int]:
    sources = read_sources(cwd, list_source_paths(cwd))
    return importers_of(count_importers(build_graph(sources)), [entry.file for entry in entries])


def run_next(cwd: Path, as_json: bool, fan_in: bool) -> str:
    """Run ``ebpy next``: rank the remaining backlog into the cheapest drain work to do next."""
    artifacts = read_ceiling_artifacts(cwd)
    if artifacts.kind == "invalid":
        raise CommandError(invalid_artifacts_message(artifacts))
    entries = [
        Suppression(file=file, rule=rule, count=count)
        for file, rules in artifacts.cells.items()
        for rule, count in rules.items()
    ]
    # Reading every source file to parse its imports is the weight of a whole-repo pass,
    # not of a command you run between edits — so it is a flag rather than the default.
    importers = _gather_importers(cwd, entries) if fan_in else {}
    plan = build_drain_plan(entries, importers)
    return json.dumps(plan.to_dict(), indent=2) if as_json else render_next(plan)
