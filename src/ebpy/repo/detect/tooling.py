"""What quality tooling is configured — read from configs, not from installs.

A tool that is installed but never configured enforces nothing, and a config
with no install behind it fails the first run loudly enough to notice. Configs
are the half worth detecting.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ...models import Framework, ToolingPresence
from ...tools import ANALYZER_NAMES

if TYPE_CHECKING:
    from collections.abc import Callable

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


def detect_tooling(
    root_entries: tuple[str, ...],
    pyproject: dict[str, Any] | None,
    configs: dict[str, str],
    workflow_text: str,
) -> ToolingPresence:
    deps = _dependency_names(pyproject)
    ruff = has_ruff_config(root_entries, pyproject)
    mypy = (
        _tool_table(pyproject, "mypy") is not None
        or "mypy.ini" in root_entries
        or ".mypy.ini" in root_entries
        or _ini_has_section(configs.get("setup.cfg"), "mypy")
    )
    pytest = (
        _tool_table(pyproject, "pytest") is not None
        or "pytest.ini" in root_entries
        or _ini_has_section(configs.get("tox.ini"), "pytest")
        or _ini_has_section(configs.get("setup.cfg"), "tool:pytest")
        or "pytest" in deps
    )
    pre_commit_text = configs.get(".pre-commit-config.yaml") or ""
    return ToolingPresence(
        ruff=ruff,
        # Ruff formats as well as lints, so its config settles formatting too.
        formatter=ruff or _tool_table(pyproject, "black") is not None or "black" in deps,
        mypy=mypy,
        mypy_strict=mypy_strict_configured(pyproject, configs),
        pytest=pytest,
        vulture=_tool_table(pyproject, "vulture") is not None or "vulture" in deps,
        pre_commit=".pre-commit-config.yaml" in root_entries,
        secret_scanning=bool(
            re.search(r"gitleaks|detect-secrets|trufflehog", workflow_text + pre_commit_text, re.IGNORECASE)
        )
        or ".gitleaks.toml" in root_entries,
        agent_instructions=tuple(name for name in _AGENT_FILES if name in root_entries),
    )


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


# Temporary bridge to the diagnosis side: maps analyzer name to the ToolingPresence field
# that indicates it is configured. Replaced by per-detector detection (ToolDetector) in
# the D increment; until then, the registry ensures we only report names that actually exist.
_ANALYZER_CONFIGURED: dict[str, Callable[[ToolingPresence], bool]] = {
    "ruff": lambda t: t.ruff,
    "mypy": lambda t: t.mypy,
}


def configured_analyzers(tooling: ToolingPresence) -> set[str]:
    """Names of analyzers that are both registered and configured in this repository."""
    return {
        name
        for name in ANALYZER_NAMES
        if name in _ANALYZER_CONFIGURED and _ANALYZER_CONFIGURED[name](tooling)
    }
