"""Generic config-parsing primitives and the repository-level signals no tool owns.

Per-tool detection lives with each tool under ``tools/``; what stays here is the
shared machinery those detectors build on — reading dependency names and config
tables out of pyproject and ini files — plus the signals that belong to the
repository rather than to any single tool: the package framework, the required
Python, pre-commit, and the agent instruction files.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ebpy.models import Framework

_AGENT_FILES = ("CLAUDE.md", "AGENTS.md", ".cursorrules")


def _tool_table(pyproject: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    table = ((pyproject or {}).get("tool") or {}).get(name)
    return table if isinstance(table, dict) else None


def _normalise(name: str) -> str:
    return name.lower().replace("_", "-")


def _names_in_requirements(items: object) -> set[str]:
    """`ruff>=0.5` and `Ruff [extra] ; python_version < "3.12"` are the same package."""
    if not isinstance(items, list):
        return set()
    matches = (re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", item) for item in items if isinstance(item, str))
    return {_normalise(match.group(1)) for match in matches if match}


def _pep621_names(pyproject: dict[str, Any] | None) -> set[str]:
    project = (pyproject or {}).get("project") or {}
    groups = [
        project.get("dependencies"),
        *(project.get("optional-dependencies") or {}).values(),
        *((pyproject or {}).get("dependency-groups") or {}).values(),
    ]
    return {name for group in groups for name in _names_in_requirements(group)}


def _poetry_names(pyproject: dict[str, Any] | None) -> set[str]:
    """Poetry declares dependencies as a table keyed by name rather than as a list."""
    poetry = _tool_table(pyproject, "poetry") or {}
    tables = [
        poetry.get("dependencies"),
        poetry.get("dev-dependencies"),
        *(
            group.get("dependencies")
            for group in (poetry.get("group") or {}).values()
            if isinstance(group, dict)
        ),
    ]
    return {_normalise(key) for table in tables if isinstance(table, dict) for key in table}


def _dependency_names(pyproject: dict[str, Any] | None) -> set[str]:
    """Collect every declared dependency name, normalised.

    Covers PEP 621 dependencies and optional groups, PEP 735 dependency-groups, and
    poetry's own tables.
    """
    return _pep621_names(pyproject) | _poetry_names(pyproject)


def _ini_has_section(text: str | None, section: str) -> bool:
    return bool(text) and bool(re.search(rf"^\[{re.escape(section)}\]", text or "", re.MULTILINE))


def pre_commit_configured(root_entries: tuple[str, ...]) -> bool:
    """Return True when a pre-commit config sits at the repository root.

    pre-commit is a repository convention rather than an analyzer, so no tool detector owns it.
    """
    return ".pre-commit-config.yaml" in root_entries


def detect_agent_instructions(root_entries: tuple[str, ...]) -> tuple[str, ...]:
    """List the agent instruction files present at the root, in the order ebpy recognises them."""
    return tuple(name for name in _AGENT_FILES if name in root_entries)


_FRAMEWORKS: tuple[tuple[str, Framework], ...] = (
    ("django", "django"),
    ("fastapi", "fastapi"),
    ("flask", "flask"),
)


def detect_framework(pyproject: dict[str, Any] | None) -> Framework:
    """Identify the web framework from the project's dependencies, or 'none'."""
    deps = _dependency_names(pyproject)
    for name, framework in _FRAMEWORKS:
        if name in deps:
            return framework
    return "none"


def requires_python(pyproject: dict[str, Any] | None) -> str | None:
    """Return the project's declared requires-python, or None when absent or not a string."""
    value = ((pyproject or {}).get("project") or {}).get("requires-python")
    return value if isinstance(value, str) else None
