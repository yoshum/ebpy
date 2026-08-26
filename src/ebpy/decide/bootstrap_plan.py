"""P1: what bootstrap would do, as data.

The plan is computed pure from a diagnosis, so ``--dry-run`` prints exactly
what a real run executes. It never overwrites a config that already exists —
the exceptions in it have reasons that are not in the file — but a skip carries
the content it declined to write, so the settings can still be applied by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from ebpy.generate.configs import DEPENDABOT_CONTENT, GITATTRIBUTES_CONTENT
from ebpy.generate.workflows import gate_workflow, run_prefix_for
from ebpy.models import Diagnosis, ToolSetup
from ebpy.package_manager import DEV_INSTALL_PREFIXES
from ebpy.tools import PROVISIONERS

from .provisioner import AddWorkflowStep, AppendText, CreateFile, ProvisionContext


@dataclass(frozen=True)
class InstallAction:
    """The dev-install command bootstrap composes from the packages provisioners request."""

    packages: tuple[str, ...]
    argv: tuple[str, ...]


@dataclass(frozen=True)
class SkippedFile:
    """A config bootstrap planned to create and did not, because that path already exists.

    The content travels with the skip rather than being dropped at the decision: the run that
    declined to write a config is the run whose reader most needs to read it, to merge by hand
    what the file already there is missing.
    """

    path: str
    content: str
    reason: str


@dataclass(frozen=True)
class BootstrapPlan:
    """What bootstrap would do, as data: the install action, the files to write, and what it skips."""

    install: InstallAction | None
    # AddWorkflowStep is never a plan file — it is folded into quality.yml by the gate workflow.
    files: tuple[CreateFile | AppendText, ...]
    skipped: tuple[SkippedFile, ...]


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
    """Decide the bootstrap plan — packages to install and files to create — from a diagnosis."""
    has_pyproject = "pyproject.toml" in root_entries
    packages = _missing_dev_packages(diagnosis)
    install = (
        InstallAction(packages=packages, argv=(*DEV_INSTALL_PREFIXES[diagnosis.package_manager], *packages))
        if packages
        else None
    )

    ctx = ProvisionContext(
        has_pyproject=has_pyproject,
        requires_python=diagnosis.requires_python,
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
    skipped: list[SkippedFile] = []

    def add(action: CreateFile | AppendText) -> None:
        # AppendText is additive (unconfigured detection already gates it); only a CreateFile
        # onto a path that already exists is skipped, so a hand-written config is never touched.
        if isinstance(action, CreateFile) and action.path in all_files:
            skipped.append(SkippedFile(action.path, action.content, action.reason))
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


_FENCE_LANGUAGES = {".toml": "toml", ".ini": "ini", ".yml": "yaml", ".yaml": "yaml"}


def _fence(content: str) -> str:
    """Return a fence longer than the longest backtick run in the content.

    A fixed three-backtick fence ends the block early on a config that contains one, handing
    the reader a truncated file that still looks whole.
    """
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def _skipped_lines(skipped: tuple[SkippedFile, ...]) -> list[str]:
    """Render each skipped config in full, so what bootstrap declined to write can still be applied.

    Nothing here is printed when nothing was skipped: a run that overwrote no config and a run
    that had no config to overwrite must not read the same.
    """
    if not skipped:
        return []
    present = "1 file" if len(skipped) == 1 else f"{len(skipped)} files"
    lines = [
        "",
        f"Left alone ({present} already present). Below is the config bootstrap would have",
        "written — merge by hand whatever the file already there is missing.",
    ]
    for entry in skipped:
        fence = _fence(entry.content)
        language = _FENCE_LANGUAGES.get(PurePosixPath(entry.path).suffix, "")
        lines.extend(
            ["", f"{entry.path} — {entry.reason}", fence + language, entry.content.rstrip("\n"), fence]
        )
    return lines


def render_plan(plan: BootstrapPlan, dry_run: bool) -> str:
    """Render a bootstrap plan as the text shown for a real run or a dry run."""
    lines = ["ebpy bootstrap" + (" --dry-run" if dry_run else ""), ""]
    if plan.install:
        lines.append(("would run:  " if dry_run else "installing: ") + " ".join(plan.install.argv))
    else:
        lines.append("nothing to install — every tool is already declared")
    for action in plan.files:
        verb = "append to" if isinstance(action, AppendText) else "write"
        prefix = f"would {verb}" if dry_run else verb
        lines.append(f"{prefix:>12} {action.path}  ({action.reason})")
    lines.extend(f"     skipped {entry.path} — already exists, not touched" for entry in plan.skipped)
    lines.extend(_skipped_lines(plan.skipped))
    if not dry_run:
        lines.extend(["", "Next: `ebpy freeze` pins today's violations as the ceiling."])
    return "\n".join([*lines, ""])
