"""Which package manager this repository actually uses, read from its lockfile."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ebpy.models import PackageManager

# Most specific first: a repo can carry requirements.txt exports next to the lockfile
# that is actually the source of truth.
_LOCKFILES: tuple[tuple[str, PackageManager], ...] = (
    ("uv.lock", "uv"),
    ("poetry.lock", "poetry"),
    ("pdm.lock", "pdm"),
    ("Pipfile.lock", "pipenv"),
    ("Pipfile", "pipenv"),
)


def detect_package_manager(root_entries: tuple[str, ...], pyproject: dict[str, Any] | None) -> PackageManager:
    """Identify the package manager in use, trusting a lockfile over a pyproject tool table."""
    for lockfile, manager in _LOCKFILES:
        if lockfile in root_entries:
            return manager
    tool = (pyproject or {}).get("tool") or {}
    if "poetry" in tool:
        return "poetry"
    if "pdm" in tool:
        return "pdm"
    if "uv" in tool:
        return "uv"
    return "pip"
