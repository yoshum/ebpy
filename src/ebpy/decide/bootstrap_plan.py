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
    MYPY_INI_CONTENT,
    MYPY_PYPROJECT_SECTION,
    python_version_from_requires,
    ruff_pyproject_section,
    ruff_toml_content,
)
from ..generate.workflows import gate_workflow, secret_scan_workflow
from ..models import Diagnosis
from ..package_manager import DEV_INSTALL_PREFIXES
from .provisioner import FileAction, InstallAction


@dataclass(frozen=True)
class BootstrapPlan:
    install: InstallAction | None
    files: tuple[FileAction, ...]
    skipped: tuple[str, ...]


def _missing_dev_packages(diagnosis: Diagnosis) -> tuple[str, ...]:
    setups = diagnosis.tool_setups
    return tuple(name for name in ("ruff", "mypy", "pytest", "vulture") if not setups[name].configured)


def _config_actions(diagnosis: Diagnosis, has_pyproject: bool) -> list[FileAction]:
    actions: list[FileAction] = []
    target = python_version_from_requires(diagnosis.requires_python)
    if not diagnosis.tool_setups["ruff"].configured:
        if has_pyproject:
            actions.append(
                FileAction(
                    path="pyproject.toml",
                    content="\n" + ruff_pyproject_section(target),
                    mode="append",
                    reason="lint + format config; the rule tiers the ratchet will freeze",
                )
            )
        else:
            actions.append(
                FileAction(
                    path="ruff.toml",
                    content=ruff_toml_content(target),
                    mode="create",
                    reason="lint + format config (no pyproject.toml to append to)",
                )
            )
    if not diagnosis.tool_setups["mypy"].configured:
        if has_pyproject:
            actions.append(
                FileAction(
                    path="pyproject.toml",
                    content="\n" + MYPY_PYPROJECT_SECTION,
                    mode="append",
                    reason="type checking, strict — errors are ratcheted per file per rule, like Ruff's",
                )
            )
        else:
            actions.append(
                FileAction(
                    path="mypy.ini",
                    content=MYPY_INI_CONTENT,
                    mode="create",
                    reason="type checking, strict (no pyproject.toml to append to)",
                )
            )
    return actions


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
