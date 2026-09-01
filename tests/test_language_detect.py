"""Language detection: what a repository contains, read from its file list alone."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ebpy.repo.detect.language import detect_languages, languages_from_files

if TYPE_CHECKING:
    from pathlib import Path


def test_a_repository_with_no_markers_detects_no_language() -> None:
    assert languages_from_files(["README.md", "LICENSE"]).languages == frozenset()


def test_a_python_source_file_at_any_depth_detects_python() -> None:
    assert languages_from_files(["src/pkg/mod.py"]).languages == frozenset({"python"})


def test_a_notebook_only_repository_detects_python() -> None:
    """Ruff walks notebooks by default, so a notebook-only repository is measured today."""
    assert languages_from_files(["analysis/run.ipynb"]).languages == frozenset({"python"})


def test_a_stub_only_repository_detects_python() -> None:
    """A .pyi-only repository is measured today; a narrower marker set would silently drop it."""
    assert languages_from_files(["stubs/thing.pyi"]).languages == frozenset({"python"})


def test_a_lockfile_alone_detects_python() -> None:
    assert languages_from_files(["uv.lock"]).languages == frozenset({"python"})


def test_a_cargo_manifest_at_any_depth_detects_rust() -> None:
    assert languages_from_files(["crates/a/Cargo.toml"]).languages == frozenset({"rust"})


def test_a_manifest_under_a_target_segment_does_not_detect_rust() -> None:
    """`target` is cargo's build directory; a manifest cargo itself wrote there is not the project."""
    assert languages_from_files(["target/package/foo-0.1.0/Cargo.toml"]).languages == frozenset()


def test_a_mixed_repository_detects_both_languages() -> None:
    files = ["pyproject.toml", "rust/Cargo.toml"]
    assert languages_from_files(files).languages == frozenset({"python", "rust"})


def test_detect_languages_reads_the_working_tree(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    assert detect_languages(tmp_path).languages == frozenset({"python", "rust"})


def test_a_rust_only_tree_does_not_detect_python(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    assert detect_languages(tmp_path).languages == frozenset({"rust"})
