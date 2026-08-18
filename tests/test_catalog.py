from __future__ import annotations

from ebpy.catalog import catalog_sources, extract_exports, render_catalog


def test_public_module_level_functions_are_catalogued() -> None:
    source = '''
def helper(x: int) -> int:
    """Doubles a number."""
    return x * 2


async def fetch() -> None:
    """Fetches the thing."""
'''
    entries = extract_exports(source, "src/util.py")
    assert [entry.name for entry in entries] == ["helper", "fetch"]
    assert entries[0].summary == "Doubles a number."


def test_private_helpers_are_not_the_shared_surface() -> None:
    entries = extract_exports("def _internal() -> None: ...\n", "a.py")
    assert entries == []


def test_methods_are_not_module_level_helpers() -> None:
    source = "class Thing:\n    def method(self) -> None: ...\n"
    assert extract_exports(source, "a.py") == []


def test_the_summary_is_the_first_sentence_not_the_first_line() -> None:
    source = '''
def wrapped() -> None:
    """Reads the ledger and
    returns what it holds. Everything after this is detail."""
'''
    entry = extract_exports(source, "a.py")[0]
    assert entry.summary == "Reads the ledger and returns what it holds."


def test_a_helper_without_a_docstring_still_appears() -> None:
    entry = extract_exports("def bare() -> None: ...\n", "a.py")[0]
    assert entry.summary is None


def test_a_file_that_does_not_parse_contributes_nothing() -> None:
    assert extract_exports("def broken(:\n", "a.py") == []


def test_tests_are_not_shared_helpers() -> None:
    paths = ["src/util.py", "tests/test_util.py", "src/test_helpers.py", "README.md"]
    assert catalog_sources(paths) == ["src/util.py"]


def test_an_empty_catalog_says_so() -> None:
    assert "No public functions found." in render_catalog([])


def test_the_catalog_groups_by_directory() -> None:
    entries = [
        *extract_exports("def a() -> None: ...\n", "src/one.py"),
        *extract_exports("def b() -> None: ...\n", "src/sub/two.py"),
    ]
    rendered = render_catalog(entries)
    assert "## src" in rendered
    assert "## src/sub" in rendered
    assert "`a`" in rendered and "`b`" in rendered
