"""How many files import each file.

The other half of "how hard is this fix" is how far it reaches: an
``ANN401``-style type fix in a module twenty files import changes a public
shape, and the errors land in files the diff never opened. Direct importers,
not transitive reach — the count is one pass over the edges, and every place it
is shown says "imported by" so the narrower claim is the one being made.

Resolution covers relative imports and absolute module paths that map onto the
repository layout (including a ``src/`` layout). A module imported solely
through a path manipulated at runtime reads low.
"""

from __future__ import annotations

import ast
from pathlib import PurePosixPath

ImportGraph = dict[str, list[str]]

Sources = dict[str, str]

_ROOT_PREFIXES = ("", "src/")


def _module_index(files: list[str]) -> dict[str, str]:
    """Dotted module name -> file path, for every file under a recognised root."""
    index: dict[str, str] = {}
    for file in files:
        for prefix in _ROOT_PREFIXES:
            if prefix and not file.startswith(prefix):
                continue
            trimmed = file[len(prefix) :]
            parts = PurePosixPath(trimmed).parts
            if not parts or not trimmed.endswith(".py"):
                continue
            if parts[-1] == "__init__.py":
                dotted = ".".join(parts[:-1])
            else:
                dotted = ".".join((*parts[:-1], parts[-1][: -len(".py")]))
            if dotted:
                index.setdefault(dotted, file)
    return index


def _package_of(file: str) -> list[str]:
    parts = list(PurePosixPath(file).parts[:-1])
    return parts


def _resolve(dotted: str, index: dict[str, str]) -> str | None:
    """A module or any of its parents: importing `a.b.c` reaches a/b/c.py when it
    exists, and a/b/__init__.py when `c` is a name defined inside the package.
    """
    candidate = dotted
    while candidate:
        if candidate in index:
            return index[candidate]
        candidate = candidate.rpartition(".")[0]
    return None


def _relative_base(file: str, level: int) -> list[str]:
    parts = _package_of(file)
    # level 1 is "this package"; each extra dot climbs one more.
    climb = level - 1
    return parts[: len(parts) - climb] if climb <= len(parts) else []


def _imports_of(source: str) -> list[tuple[str, int]]:
    """(dotted, level) pairs. Parse failures yield nothing — a file that does not parse
    imports nothing we can see, and the fan-in count should say low, not crash.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    found.append((node.module, 0))
                    found.extend((f"{node.module}.{alias.name}", 0) for alias in node.names)
            else:
                base = node.module or ""
                found.append((base, node.level))
                found.extend(
                    (f"{base}.{alias.name}" if base else alias.name, node.level) for alias in node.names
                )
    return found


def build_graph(sources: Sources) -> ImportGraph:
    """File -> the project files it imports."""
    files = sorted(sources)
    index = _module_index(files)
    graph: ImportGraph = {file: [] for file in files}
    for file, source in sources.items():
        strip = next((prefix for prefix in _ROOT_PREFIXES[1:] if file.startswith(prefix)), "")
        for dotted, level in _imports_of(source):
            if level == 0:
                resolved = _resolve(dotted, index)
            else:
                base_file = file[len(strip) :] if strip else file
                base = _relative_base(base_file, level)
                absolute = ".".join([*base, dotted]) if dotted else ".".join(base)
                resolved = _resolve(absolute, index)
            if resolved and resolved != file:
                graph[file].append(resolved)
    return graph


def count_importers(graph: ImportGraph) -> dict[str, int]:
    importers = dict.fromkeys(graph, 0)
    for dependencies in graph.values():
        for dependency in set(dependencies):
            importers[dependency] = importers.get(dependency, 0) + 1
    return importers


def importers_of(importers: dict[str, int], files: list[str]) -> dict[str, int]:
    """Only the files in the backlog, so --json carries what the ranking is about and
    not the whole repository.
    """
    return {file: importers.get(file, 0) for file in sorted(set(files))}
