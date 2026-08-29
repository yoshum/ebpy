"""D-9: placing a reported clippy path in the ceiling's coordinate system, or refusing to."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ebpy.tools.clippy._errors import ClippyInvalidOutputError
from ebpy.tools.clippy._paths import attribute_path, normalize_out_dir

if TYPE_CHECKING:
    from pathlib import Path


def _place(tmp_path: Path, relative: str) -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("pub fn f() {}\n", encoding="utf-8")


def _verdict(
    tmp_path: Path, reported: str, root: str = "", out_dirs: tuple[str, ...] = ()
) -> tuple[str, str]:
    result = attribute_path(reported, workspace_root=root, repo_root=tmp_path, out_dirs=out_dirs)
    return result.kind, result.path


def test_a_path_inside_the_repository_becomes_a_cell(tmp_path: Path) -> None:
    _place(tmp_path, "src/lib.rs")
    assert _verdict(tmp_path, "src/lib.rs") == ("cell", "src/lib.rs")


def test_the_workspace_root_is_prefixed_before_the_path_is_used(tmp_path: Path) -> None:
    """Clippy reports relative to its workspace root, which is not the repository root."""
    _place(tmp_path, "crates/a/src/lib.rs")
    assert _verdict(tmp_path, "src/lib.rs", root="crates/a") == ("cell", "crates/a/src/lib.rs")


def test_a_parent_segment_that_stays_inside_the_repository_becomes_a_cell(tmp_path: Path) -> None:
    _place(tmp_path, "crates/shared/src/lib.rs")
    assert _verdict(tmp_path, "../shared/src/lib.rs", root="crates/a") == (
        "cell",
        "crates/shared/src/lib.rs",
    )


def test_a_leading_parent_segment_is_kept_until_the_root_is_prefixed(tmp_path: Path) -> None:
    """Refusing a leading `..` at step 3 would drop a legitimate `[lib] path = "../shared"`."""
    _place(tmp_path, "shared/src/lib.rs")
    assert _verdict(tmp_path, "../shared/src/lib.rs", root="crates") == ("cell", "shared/src/lib.rs")


def test_a_path_escaping_the_repository_is_unattributed(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "../../../etc/passwd.rs", root="crates/a")[0] == "unattributed"


def test_an_absolute_posix_path_is_unattributed(tmp_path: Path) -> None:
    """Absolute is the signal of a configuration ebpy does not measure; refusing is the diagnosis."""
    assert _verdict(tmp_path, "/etc/passwd.rs")[0] == "unattributed"


def test_a_windows_drive_path_is_unattributed(tmp_path: Path) -> None:
    """`C:/x.rs` is not absolute to PurePosixPath, so one flavour is not enough."""
    assert _verdict(tmp_path, "C:\\outside\\file.rs")[0] == "unattributed"


def test_a_drive_relative_path_is_unattributed(tmp_path: Path) -> None:
    """`C:foo.rs` is absolute in neither flavour; only the drive gives it away."""
    assert _verdict(tmp_path, "C:foo.rs")[0] == "unattributed"


def test_a_unc_path_is_unattributed(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "//server/share/x.rs")[0] == "unattributed"


def test_a_path_that_collapses_to_nothing_is_unattributed(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "foo/..")[0] == "unattributed"


def test_a_path_collapsing_to_nothing_under_a_nested_root_is_still_unattributed(tmp_path: Path) -> None:
    """One collapse after prefixing turns `foo/..` into the directory `crates/a`."""
    (tmp_path / "crates" / "a").mkdir(parents=True)
    assert _verdict(tmp_path, "foo/..", root="crates/a")[0] == "unattributed"


def test_a_path_that_names_no_file_is_unattributed(tmp_path: Path) -> None:
    for reported in ("..", "../foo/.."):
        assert _verdict(tmp_path, reported, root="crates/a")[0] == "unattributed"


def test_a_remapped_path_that_does_not_exist_is_unattributed(tmp_path: Path) -> None:
    """`--remap-path-prefix=src=shadow` rewrites the text and still exits 0 with success=true."""
    _place(tmp_path, "src/lib.rs")
    assert _verdict(tmp_path, "shadow/lib.rs")[0] == "unattributed"


def test_generated_code_under_a_reported_out_dir_is_dropped_silently(tmp_path: Path) -> None:
    """A build script's output is not source; unattributed would make freeze refuse forever."""
    out = "/build/x-abc/out"
    assert _verdict(tmp_path, f"{out}/gen.rs", out_dirs=(out,)) == ("generated", "")


def test_an_out_dir_match_respects_segment_boundaries(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "/build/outside.rs", out_dirs=("/build/out",))[0] == "unattributed"


def test_an_out_dir_is_normalized_before_it_is_compared() -> None:
    """Without this, a backslash-separated out_dir never matches a forward-slashed diagnostic."""
    assert normalize_out_dir("C:\\repo\\target\\debug\\build\\x\\out") == "C:/repo/target/debug/build/x/out"
    assert normalize_out_dir("/repo/target/./debug/../debug/build/x/out/") == (
        "/repo/target/debug/build/x/out"
    )


def test_a_relative_out_dir_is_invalid_output() -> None:
    """Cargo documents out_dir as absolute; a relative one means ebpy is misreading the stream."""
    with pytest.raises(ClippyInvalidOutputError):
        normalize_out_dir("target/debug/build/x/out")


def test_a_path_that_resolves_outside_the_repository_is_unattributed(tmp_path: Path) -> None:
    """A ceiling keyed on this host's symlink resolution would not reproduce anywhere else."""
    outside = tmp_path.parent / "outside_target"
    outside.mkdir(exist_ok=True)
    (outside / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    assert _verdict(tmp_path, "link/lib.rs")[0] == "unattributed"


def test_a_nul_byte_in_a_path_is_unattributed_not_an_exception(tmp_path: Path) -> None:
    """Clippy's output is external input; a raw ValueError must not escape the parser."""
    assert _verdict(tmp_path, "src/li\x00b.rs")[0] == "unattributed"
