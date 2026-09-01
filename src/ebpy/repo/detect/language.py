"""Which languages a repository contains, as a function of its file list.

Detection never runs a subprocess. A machine without a language's toolchain must still be
able to measure the half of a mixed repository it can reach, so a missing toolchain is that
analyzer's availability — not a failure of language detection.
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

# Deliberately wide. For Python, too wide only means ruff and mypy report "nothing here";
# too narrow means a repository ebpy gates today silently falls out of scope. `.ipynb` is
# here because `ruff check .` already walks notebooks, and `.pyi`/`.pyw` because today's
# unscoped `measure_repository` measures a stub-only repository. The same width is applied
# to Rust detection below (any non-`target` `Cargo.toml` counts), but there "too wide" is not
# harmless: clippy fails closed on a manifest that is not a resolvable crate, rather than
# reporting nothing. `tools/clippy/_runner.py` and `_topology.py` name the recovery —
# declaring a narrower `analyzers` set in `.ebpy/config.json` — for exactly that case.
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


def no_python_message(command: str) -> str:
    """Explain why a Python-only command will not run here.

    Refusing rather than returning empty results: every one of these reads `.py` files and
    would otherwise report "nobody looked" as "zero" — a cargo project shown as using pip,
    or "0 files over 600 lines" for a repository with no Python files to count.
    """
    return "\n".join(
        [
            f"`ebpy {command}` reads Python sources, and this repository has none.",
            "Its answer would be an empty result rather than a finding, so nothing was run.",
            "`ebpy freeze`, `check`, `prune`, `report`, `status`, `log`, `secrets` and `next`",
            "all work here.",
        ]
    )
