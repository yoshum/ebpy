"""P1: install what is missing, generate the configs. ``--dry-run`` touches nothing."""

from __future__ import annotations

from pathlib import Path

from ..decide.bootstrap_plan import BootstrapPlan, build_plan, render_plan
from ..decide.diagnose import diagnose
from ..repo.facts import gather_facts
from ..util import run


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
        if action.mode == "append":
            existing = target.read_text(encoding="utf-8") if target.is_file() else ""
            target.write_text(existing + action.content, encoding="utf-8")
        else:
            target.write_text(action.content, encoding="utf-8")
    return problems


def run_bootstrap(cwd: Path, dry_run: bool, python_version: str) -> str:
    facts = gather_facts(cwd)
    # The plan reads only the tool setups and required Python; the roster feeds the
    # "configured but not ratcheted" gap, which the plan ignores, so an empty roster is enough.
    diagnosis = diagnose(facts, ())
    plan = build_plan(diagnosis, facts.root_entries, facts.all_files, python_version)
    output = render_plan(plan, dry_run)
    if dry_run:
        return output
    problems = _apply(cwd, plan)
    if problems:
        return "\n".join([output, *problems])
    return output
