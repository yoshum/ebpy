"""Write docs/shared-helpers.md — every public function, so nobody writes a sixth."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ebpy.catalog import CatalogEntry, catalog_sources, extract_exports, render_catalog
from ebpy.errors import CommandError
from ebpy.repo.detect.language import has_python, no_python_message
from ebpy.repo.facts import list_source_paths, read_sources

if TYPE_CHECKING:
    from pathlib import Path

CATALOG_FILE = "docs/shared-helpers.md"


def run_catalog(cwd: Path) -> str:
    """Run ``ebpy catalog``: regenerate docs/shared-helpers.md from the public functions in source."""
    if not has_python(cwd):
        raise CommandError(no_python_message("catalog"))
    sources = read_sources(cwd, catalog_sources(list_source_paths(cwd)))
    entries: list[CatalogEntry] = []
    for path, text in sorted(sources.items()):
        entries.extend(extract_exports(text, path))
    target = cwd / CATALOG_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_catalog(entries), encoding="utf-8")
    return f"Wrote {CATALOG_FILE}: {len(entries)} public functions across {len(sources)} files."
