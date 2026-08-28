"""Everything read from disk, in one value.

Every decision function in ``diagnose`` takes this and returns a verdict, so
the decisions are pure and the disk access lives in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from ebpy._toml import TOMLDecodeError, loads
from ebpy.models import SourceFile, WorkflowFile

from .git import tracked_files

_SKIPPED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
    "build",
    "dist",
}


@dataclass(frozen=True)
class RepoFacts:
    """Everything read from disk once, so decisions stay pure: the tree, pyproject, sources and workflows."""

    cwd: Path
    # Repo-relative names of files in the repository root (not recursive).
    root_entries: tuple[str, ...]
    # Every tracked, non-ignored file. root_entries cannot answer questions about subdirectories.
    all_files: tuple[str, ...]
    pyproject: dict[str, Any] | None
    source_files: tuple[SourceFile, ...]
    workflows: tuple[WorkflowFile, ...]
    extra_config_text: dict[str, str] = field(default_factory=dict)


def _walk_files(cwd: Path) -> list[str]:
    found: list[str] = []
    stack = [cwd]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name in _SKIPPED_DIRS:
                continue
            if entry.is_dir():
                stack.append(entry)
            elif entry.is_file():
                found.append(str(PurePosixPath(entry.relative_to(cwd))))
    return found


def list_all_files(cwd: Path) -> list[str]:
    """Return every tracked, non-ignored file, falling back to a filesystem walk outside a git repo."""
    tracked = tracked_files(cwd)
    if tracked is not None:
        return [f.replace("\\", "/") for f in tracked]
    return _walk_files(cwd)


def _count_lines(path: Path) -> int:
    try:
        return path.read_text(encoding="utf-8", errors="replace").count("\n") + 1
    except OSError:
        return 0


def list_source_paths(cwd: Path) -> list[str]:
    """Return the repo-relative paths of every Python source file."""
    return [file for file in list_all_files(cwd) if file.endswith(".py")]


def read_sources(cwd: Path, paths: list[str]) -> dict[str, str]:
    """Read the given paths' text, skipping any that cannot be read."""
    sources: dict[str, str] = {}
    for path in paths:
        try:
            sources[path] = (cwd / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return sources


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


_EXTRA_CONFIGS = (
    "ruff.toml",
    ".ruff.toml",
    "mypy.ini",
    ".mypy.ini",
    "setup.cfg",
    "tox.ini",
    "pytest.ini",
    ".pre-commit-config.yaml",
)


def gather_facts(cwd: Path) -> RepoFacts:
    """Read everything a diagnosis needs from disk once, so the decision functions stay pure."""
    all_files = list_all_files(cwd)
    root_entries = tuple(sorted({file for file in all_files if "/" not in file}))

    pyproject: dict[str, Any] | None = None
    pyproject_path = cwd / "pyproject.toml"
    if pyproject_path.is_file():
        try:
            pyproject = loads(pyproject_path.read_text(encoding="utf-8"))
        except (OSError, TOMLDecodeError):
            pyproject = None

    source_files = tuple(
        SourceFile(path=file, lines=_count_lines(cwd / file)) for file in all_files if file.endswith(".py")
    )

    workflows = tuple(
        WorkflowFile(path=file, content=_read_text(cwd / file) or "")
        for file in all_files
        if file.startswith(".github/workflows/") and file.endswith((".yml", ".yaml"))
    )

    extra = {name: text for name in _EXTRA_CONFIGS if (text := _read_text(cwd / name)) is not None}

    return RepoFacts(
        cwd=cwd,
        root_entries=root_entries,
        all_files=tuple(all_files),
        pyproject=pyproject,
        source_files=source_files,
        workflows=workflows,
        extra_config_text=extra,
    )
