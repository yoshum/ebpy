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
from ..generate.workflows import gate_workflow, secret_scan_workflow
from ..models import Diagnosis, ToolSetup
from ..package_manager import DEV_INSTALL_PREFIXES
from ..tools import PROVISIONERS
from .provisioner import FileAction, InstallAction


@dataclass(frozen=True)
class BootstrapPlan:
    install: InstallAction | None
    files: tuple[FileAction, ...]
    skipped: tuple[str, ...]


def _missing_dev_packages(diagnosis: Diagnosis) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            pkg
            for p in PROVISIONERS
            for pkg in p.packages(diagnosis.tool_setups.get(p.name, ToolSetup(configured=False)))
        )
    )


def _config_actions(diagnosis: Diagnosis, has_pyproject: bool) -> list[FileAction]:
    target = python_version_from_requires(diagnosis.requires_python)
    return [
        action
        for p in PROVISIONERS
        for action in p.config_actions(
            diagnosis.tool_setups.get(p.name, ToolSetup(configured=False)),
            has_pyproject,
            target,
        )
    ]


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

    files = _config_actions(diagnosis, has_pyproject)
    skipped: list[str] = []

    def create(path: str, content: str, reason: str) -> None:
        if path in all_files:
            skipped.append(f"{path} — already exists, not touched")
        else:
            files.append(FileAction(path=path, content=content, mode="create", reason=reason))

    create(
        ".github/workflows/quality.yml",
        gate_workflow(diagnosis.package_manager, python_version),
        "the gate: lint, typecheck, test and `ebpy check` on three platforms",
    )
    create(
        ".github/workflows/secret-scan.yml",
        secret_scan_workflow(),
        "gitleaks over history and working tree — the one check with no baseline",
    )
    create(".github/dependabot.yml", DEPENDABOT_CONTENT, "keeps the pinned versions current later")
    create(".gitattributes", GITATTRIBUTES_CONTENT, "line endings settled once, per repository")

    return BootstrapPlan(install=install, files=tuple(files), skipped=tuple(skipped))


def render_plan(plan: BootstrapPlan, dry_run: bool) -> str:
    lines = ["ebpy bootstrap" + (" --dry-run" if dry_run else ""), ""]
    if plan.install:
        lines.append(("would run:  " if dry_run else "installing: ") + " ".join(plan.install.argv))
    else:
        lines.append("nothing to install — every tool is already declared")
    for action in plan.files:
        verb = "append to" if action.mode == "append" else "write"
        prefix = f"would {verb}" if dry_run else verb
        lines.append(f"{prefix:>12} {action.path}  ({action.reason})")
    lines.extend(f"     skipped {note}" for note in plan.skipped)
    if not dry_run:
        lines.extend(["", "Next: `ebpy freeze` pins today's violations as the ceiling."])
    return "\n".join([*lines, ""])
