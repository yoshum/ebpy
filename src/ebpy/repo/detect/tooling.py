"""What quality tooling is configured — read from configs, not from installs.

A tool that is installed but never configured enforces nothing, and a config
with no install behind it fails the first run loudly enough to notice. Configs
are the half worth detecting.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...models import Framework

_AGENT_FILES = ("CLAUDE.md", "AGENTS.md", ".cursorrules")


def _tool_table(pyproject: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    table = ((pyproject or {}).get("tool") or {}).get(name)
    return table if isinstance(table, dict) else None


def _normalise(name: str) -> str:
    return name.lower().replace("_", "-")


def _names_in_requirements(items: Any) -> set[str]:
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
    """Every declared dependency name, normalised: PEP 621 dependencies and optional
    groups, PEP 735 dependency-groups, and poetry's own tables."""
    return _pep621_names(pyproject) | _poetry_names(pyproject)


def _ini_has_section(text: str | None, section: str) -> bool:
    return bool(text) and bool(re.search(rf"^\[{re.escape(section)}\]", text or "", re.MULTILINE))


def has_ruff_config(root_entries: tuple[str, ...], pyproject: dict[str, Any] | None) -> bool:
    return (
        "ruff.toml" in root_entries
        or ".ruff.toml" in root_entries
        or _tool_table(pyproject, "ruff") is not None
    )


def mypy_strict_configured(pyproject: dict[str, Any] | None, configs: dict[str, str]) -> bool:
    table = _tool_table(pyproject, "mypy")
    if table is not None and table.get("strict") is True:
        return True
    for name in ("mypy.ini", ".mypy.ini", "setup.cfg"):
        text = configs.get(name)
        if text and re.search(r"^\s*strict\s*=\s*[Tt]rue", text, re.MULTILINE):
            return True
    return False


def mypy_configured(
    root_entries: tuple[str, ...],
    pyproject: dict[str, Any] | None,
    configs: dict[str, str],
) -> bool:
    """Return True if any mypy configuration is present in standard locations."""
    return (
        _tool_table(pyproject, "mypy") is not None
        or "mypy.ini" in root_entries
        or ".mypy.ini" in root_entries
        or _ini_has_section(configs.get("setup.cfg"), "mypy")
    )


def formatter_configured(root_entries: tuple[str, ...], pyproject: dict[str, Any] | None) -> bool:
    """Return True when a formatter (ruff or black) is configured."""
    # Ruff formats as well as lints, so its config settles formatting too.
    deps = _dependency_names(pyproject)
    return (
        has_ruff_config(root_entries, pyproject)
        or _tool_table(pyproject, "black") is not None
        or "black" in deps
    )


def pytest_configured(
    root_entries: tuple[str, ...],
    pyproject: dict[str, Any] | None,
    configs: dict[str, str],
) -> bool:
    """Return True when pytest is configured via any standard mechanism."""
    deps = _dependency_names(pyproject)
    return (
        _tool_table(pyproject, "pytest") is not None
        or "pytest.ini" in root_entries
        or _ini_has_section(configs.get("tox.ini"), "pytest")
        or _ini_has_section(configs.get("setup.cfg"), "tool:pytest")
        or "pytest" in deps
    )


def vulture_configured(pyproject: dict[str, Any] | None) -> bool:
    """Return True when vulture is configured or declared as a dependency."""
    deps = _dependency_names(pyproject)
    return _tool_table(pyproject, "vulture") is not None or "vulture" in deps


def secret_scan_configured(root_entries: tuple[str, ...], workflow_text: str, pre_commit_text: str) -> bool:
    """Return True when a known secret-scanning tool is referenced in workflows or pre-commit config."""
    return (
        bool(re.search(r"gitleaks|detect-secrets|trufflehog", workflow_text + pre_commit_text, re.IGNORECASE))
        or ".gitleaks.toml" in root_entries
    )


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
    deps = _dependency_names(pyproject)
    for name, framework in _FRAMEWORKS:
        if name in deps:
            return framework
    return "none"


def requires_python(pyproject: dict[str, Any] | None) -> str | None:
    value = ((pyproject or {}).get("project") or {}).get("requires-python")
    return value if isinstance(value, str) else None
