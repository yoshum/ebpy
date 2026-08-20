from __future__ import annotations

from ebpy.repo.fan_in import build_graph, count_importers, importers_of


def test_absolute_imports_resolve_onto_the_repo_layout() -> None:
    sources = {
        "pkg/__init__.py": "",
        "pkg/util.py": "def helper() -> None: ...",
        "pkg/a.py": "from pkg.util import helper",
        "pkg/b.py": "import pkg.util",
    }
    importers = count_importers(build_graph(sources))
    assert importers["pkg/util.py"] == 2


def test_a_src_layout_resolves_the_same_way() -> None:
    sources = {
        "src/pkg/util.py": "",
        "src/pkg/a.py": "from pkg.util import helper",
    }
    importers = count_importers(build_graph(sources))
    assert importers["src/pkg/util.py"] == 1


def test_relative_imports_resolve() -> None:
    sources = {
        "pkg/util.py": "",
        "pkg/sub/__init__.py": "",
        "pkg/sub/a.py": "from ..util import helper",
        "pkg/b.py": "from .util import helper",
    }
    importers = count_importers(build_graph(sources))
    assert importers["pkg/util.py"] == 2


def test_a_name_imported_from_a_package_counts_against_its_init() -> None:
    sources = {
        "pkg/__init__.py": "helper = 1",
        "pkg/a.py": "from pkg import helper",
    }
    importers = count_importers(build_graph(sources))
    assert importers["pkg/__init__.py"] == 1


def test_third_party_imports_resolve_to_nothing() -> None:
    sources = {"a.py": "import os\nimport requests\n"}
    assert build_graph(sources) == {"a.py": []}


def test_a_file_importing_itself_is_not_counted() -> None:
    sources = {"pkg/a.py": "import pkg.a"}
    assert count_importers(build_graph(sources))["pkg/a.py"] == 0


def test_a_file_that_does_not_parse_reads_low_rather_than_crashing() -> None:
    sources = {"broken.py": "def f(:", "ok.py": "x = 1"}
    graph = build_graph(sources)
    assert graph["broken.py"] == []


def test_importers_of_reports_only_the_backlog_files() -> None:
    counts = {"a.py": 3, "b.py": 0, "c.py": 9}
    assert importers_of(counts, ["c.py", "a.py", "a.py"]) == {"a.py": 3, "c.py": 9}


def test_a_file_outside_the_graph_reports_zero_not_a_missing_key() -> None:
    assert importers_of({}, ["gone.py"]) == {"gone.py": 0}
