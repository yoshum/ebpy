"""P1: install what is missing, generate the configs. ``--dry-run`` touches nothing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ebpy.decide.bootstrap_plan import BootstrapPlan, build_plan, render_plan
from ebpy.decide.diagnose import diagnose
from ebpy.decide.provisioner import AppendText
from ebpy.errors import CommandError
from ebpy.repo.detect.language import languages_from_files, no_python_message
from ebpy.repo.facts import gather_facts
from ebpy.util import run

if TYPE_CHECKING:
    from pathlib import Path


def _apply(cwd: Path, plan: BootstrapPlan) -> list[str]:
    problems: list[str] = []
    if plan.install:
        result = run(list(plan.install.argv), cwd)
        if result.code != 0:
            problems.append(
                f"install failed (exit {result.code}): {' '.join(plan.install.argv)}\n{result.stderr[:2000]}"
            )
    for action in plan.files:
        target = cwd / action.path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(action, AppendText):
            existing = target.read_text(encoding="utf-8") if target.is_file() else ""
            target.write_text(existing + action.content, encoding="utf-8")
        else:
            target.write_text(action.content, encoding="utf-8")
    return problems


def run_bootstrap(cwd: Path, dry_run: bool, python_version: str) -> str:
    """Run ``ebpy bootstrap``: plan the toolchain setup and, unless a dry run, apply it."""
    facts = gather_facts(cwd)
    languages = languages_from_files(facts.all_files)
    if "python" not in languages.languages:
        raise CommandError(no_python_message("bootstrap"))
    # The plan reads only the tool setups and required Python; the roster feeds the
    # "configured but not ratcheted" gap, which the plan ignores, so an empty roster is enough.
    diagnosis = diagnose(facts, (), languages.languages)
    plan = build_plan(diagnosis, facts.root_entries, facts.all_files, python_version)
    output = render_plan(plan, dry_run)
    if dry_run:
        return output
    problems = _apply(cwd, plan)
    if problems:
        return "\n".join([output, *problems])
    return output
