"""P1: what bootstrap would do, as data.

The plan is computed pure from a diagnosis, so ``--dry-run`` prints exactly
what a real run executes. It never overwrites a config that already exists —
the exceptions in it have reasons that are not in the file.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..generate.configs import (
    DEPENDABOT_CONTENT,
    GITATTRIBUTES_CONTENT,
    python_version_from_requires,
)
from ..generate.workflows import gate_workflow, run_prefix_for
from ..models import Diagnosis, ToolSetup
from ..package_manager import DEV_INSTALL_PREFIXES
from ..tools import PROVISIONERS
from .provisioner import AddWorkflowStep, AppendText, CreateFile, ProvisionContext


@dataclass(frozen=True)
class InstallAction:
    """The dev-install command bootstrap composes from the packages provisioners request."""

    packages: tuple[str, ...]
    argv: tuple[str, ...]


@dataclass(frozen=True)
class BootstrapPlan:
    """What bootstrap would do, as data: the install action, the files to write, and what it skips."""

    install: InstallAction | None
    # AddWorkflowStep is never a plan file — it is folded into quality.yml by the gate workflow.
    files: tuple[CreateFile | AppendText, ...]
    skipped: tuple[str, ...]


def _missing_dev_packages(diagnosis: Diagnosis) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            pkg
            for p in PROVISIONERS
            for pkg in p.plan_packages(diagnosis.tool_setups.get(p.name, ToolSetup(configured=False)))
        )
    )


def build_plan(
    diagnosis: Diagnosis,
    root_entries: tuple[str, ...],
    all_files: tuple[str, ...],
    python_version: str,
) -> BootstrapPlan:
    has_pyproject = "pyproject.toml" in root_entries
    packages = _missing_dev_packages(diagnosis)
    install = (
        InstallAction(packages=packages, argv=(*DEV_INSTALL_PREFIXES[diagnosis.package_manager], *packages))
        if packages
        else None
    )

    ctx = ProvisionContext(
        has_pyproject=has_pyproject,
        target_version=python_version_from_requires(diagnosis.requires_python),
        run_prefix=run_prefix_for(diagnosis.package_manager),
    )
    gate_steps: list[str] = []
    tool_files: list[CreateFile | AppendText] = []
    for p in PROVISIONERS:
        setup = diagnosis.tool_setups.get(p.name, ToolSetup(configured=False))
        for action in p.plan_file_actions(setup, ctx):
            if isinstance(action, AddWorkflowStep):
                gate_steps.extend(action.lines)
            else:
                tool_files.append(action)

    files: list[CreateFile | AppendText] = []
    skipped: list[str] = []

    def add(action: CreateFile | AppendText) -> None:
        # AppendText is additive (unconfigured detection already gates it); only a CreateFile
        # onto a path that already exists is skipped, so a hand-written config is never touched.
        if isinstance(action, CreateFile) and action.path in all_files:
            skipped.append(f"{action.path} — already exists, not touched")
        else:
            files.append(action)

    for action in tool_files:
        add(action)

    # ebpy-owned scaffolding, tool-agnostic: the gate wraps the steps provisioners contributed.
    add(
        CreateFile(
            ".github/workflows/quality.yml",
            gate_workflow(diagnosis.package_manager, gate_steps, python_version),
            "the gate: lint, typecheck, test and `ebpy check` on three platforms",
        )
    )
    add(CreateFile(".github/dependabot.yml", DEPENDABOT_CONTENT, "keeps the pinned versions current later"))
    add(CreateFile(".gitattributes", GITATTRIBUTES_CONTENT, "line endings settled once, per repository"))

    return BootstrapPlan(install=install, files=tuple(files), skipped=tuple(skipped))


def render_plan(plan: BootstrapPlan, dry_run: bool) -> str:
    lines = ["ebpy bootstrap" + (" --dry-run" if dry_run else ""), ""]
    if plan.install:
        lines.append(("would run:  " if dry_run else "installing: ") + " ".join(plan.install.argv))
    else:
        lines.append("nothing to install — every tool is already declared")
    for action in plan.files:
        verb = "append to" if isinstance(action, AppendText) else "write"
        prefix = f"would {verb}" if dry_run else verb
        lines.append(f"{prefix:>12} {action.path}  ({action.reason})")
    lines.extend(f"     skipped {note}" for note in plan.skipped)
    if not dry_run:
        lines.extend(["", "Next: `ebpy freeze` pins today's violations as the ceiling."])
    return "\n".join([*lines, ""])
