"""Which languages a repository contains, as a function of its file list.

Detection never runs a subprocess. A machine without cargo must still be able to measure
the Python half of a mixed repository, so cargo's absence is clippy's availability — not a
failure of language detection. Confirming where the Cargo workspaces actually are is the
clippy runner's job (`tools/clippy/_topology.py`), and that one can fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ebpy.repo.facts import list_all_files

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from ebpy.models import Language

# Deliberately wide. Too wide only means ruff and mypy report "nothing here"; too narrow
# means a repository ebpy gates today silently falls out of scope. `.ipynb` is here because
# `ruff check .` already walks notebooks, and `.pyi`/`.pyw` because today's unscoped
# `measure_repository` measures a stub-only repository.
_PYTHON_SUFFIXES = (".py", ".pyi", ".pyw", ".ipynb")

_PYTHON_NAMES = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Pipfile",
        "Pipfile.lock",
        "ruff.toml",
        ".ruff.toml",
        "mypy.ini",
        ".mypy.ini",
        "uv.lock",
        "poetry.lock",
        "pdm.lock",
    }
)

_CARGO_MANIFEST = "Cargo.toml"

# Excluded by path segment, not by prefix: the claim is "a segment named `target`", which is
# all the arithmetic supports. A repository that renamed its target directory keeps those
# manifests as candidates, and `cargo metadata` rejects or de-duplicates them later.
_RUST_EXCLUDED_SEGMENT = "target"


@dataclass(frozen=True)
class RepoLanguages:
    """The languages found in one repository."""

    languages: frozenset[Language]


def _is_python_marker(file: str) -> bool:
    name = PurePosixPath(file).name
    return (
        file.endswith(_PYTHON_SUFFIXES)
        or name in _PYTHON_NAMES
        or (name.startswith("requirements") and name.endswith(".txt"))
    )


def _is_rust_marker(file: str) -> bool:
    parts = PurePosixPath(file).parts
    return bool(parts) and parts[-1] == _CARGO_MANIFEST and _RUST_EXCLUDED_SEGMENT not in parts[:-1]


def languages_from_files(all_files: Iterable[str]) -> RepoLanguages:
    """Return the languages these files evidence. Pure: for callers that already listed the tree."""
    found: set[Language] = set()
    for file in all_files:
        if "python" not in found and _is_python_marker(file):
            found.add("python")
        if "rust" not in found and _is_rust_marker(file):
            found.add("rust")
    return RepoLanguages(languages=frozenset(found))


def detect_languages(cwd: Path) -> RepoLanguages:
    """Return the languages in the repository at cwd, for callers holding no RepoFacts."""
    return languages_from_files(list_all_files(cwd))


def has_python(cwd: Path) -> bool:
    """Report whether the repository at cwd contains Python."""
    return "python" in detect_languages(cwd).languages


def has_rust(cwd: Path) -> bool:
    """Report whether the repository at cwd contains Rust."""
    return "rust" in detect_languages(cwd).languages
