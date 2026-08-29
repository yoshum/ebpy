"""One `cargo clippy` invocation's stdout into one AnalysisMeasurement."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import pytest

from ebpy.tools.clippy._errors import ClippyFailedError, ClippyInvalidOutputError
from ebpy.tools.clippy._parser import parse_clippy_output
from ebpy.tools.clippy._topology import RustWorkspace

if TYPE_CHECKING:
    from ebpy.models import AnalysisMeasurement

WORKSPACE = RustWorkspace(root=PurePosixPath("."), target_directory=Path("/t"), packages=(".",))


def _line(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


def _warning(file: str, code: str = "clippy::needless_return", line: int = 1) -> str:
    return _line(
        {
            "reason": "compiler-message",
            "message": {
                "level": "warning",
                "message": "needless return",
                "rendered": "warning: needless return",
                "code": {"code": code},
                "spans": [{"is_primary": True, "file_name": file, "line_start": line, "column_start": 1}],
            },
        }
    )


def _error(*, spans: bool = True, configured_out: bool = False, rendered: str = "error: boom") -> str:
    children = (
        [{"message": "found an item that was configured out"}] if configured_out else [{"message": "note"}]
    )
    return _line(
        {
            "reason": "compiler-message",
            "message": {
                "level": "error",
                "message": "boom",
                "rendered": rendered,
                "code": None,
                "spans": [{"is_primary": True, "file_name": "src/lib.rs", "line_start": 1, "column_start": 1}]
                if spans
                else [],
                "children": children,
            },
        }
    )


_FINISHED_OK = _line({"reason": "build-finished", "success": True})
_FINISHED_BAD = _line({"reason": "build-finished", "success": False})


def _parse(stdout: str, tmp_path: Path, *, stderr: str = "", code: int = 0) -> AnalysisMeasurement:
    return parse_clippy_output(stdout, stderr, code, workspace=WORKSPACE, repo_root=tmp_path)


def test_a_warning_with_a_primary_span_becomes_a_cell(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    result = _parse("\n".join([_warning("src/lib.rs"), _FINISHED_OK]), tmp_path)
    assert result.cells == {"src/lib.rs": {"clippy:clippy::needless_return": 1}}


def test_the_clippy_prefix_is_kept_in_the_rule_id(tmp_path: Path) -> None:
    """Rustc's own lints share this stream; stripping `clippy::` merges two namespaces."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    result = _parse("\n".join([_warning("src/lib.rs", code="unused_variables"), _FINISHED_OK]), tmp_path)
    assert "clippy:unused_variables" in result.cells["src/lib.rs"]


def test_a_line_that_does_not_start_with_a_brace_is_ignored(tmp_path: Path) -> None:
    """A procedural macro writing to stdout lands in this stream; cargo documents the `{` test."""
    stdout = "\n".join(["hello from a macro", _FINISHED_OK])
    assert _parse(stdout, tmp_path).cells == {}


def test_a_brace_line_that_is_not_json_is_invalid_output(tmp_path: Path) -> None:
    with pytest.raises(ClippyInvalidOutputError):
        _parse("\n".join(["{not json", _FINISHED_OK]), tmp_path)


def test_output_with_no_json_object_at_all_is_execution_failed(tmp_path: Path) -> None:
    """Cargo dying silently is the tool failing, not ebpy failing to read it."""
    with pytest.raises(ClippyFailedError) as caught:
        _parse("plain text\n", tmp_path, code=101)
    assert not isinstance(caught.value, ClippyInvalidOutputError)


def test_a_missing_build_finished_is_invalid_output(tmp_path: Path) -> None:
    with pytest.raises(ClippyInvalidOutputError):
        _parse(_warning("src/lib.rs"), tmp_path)


def test_two_build_finished_messages_are_invalid_output(tmp_path: Path) -> None:
    with pytest.raises(ClippyInvalidOutputError):
        _parse("\n".join([_FINISHED_OK, _FINISHED_OK]), tmp_path)


def test_a_non_boolean_success_is_invalid_output(tmp_path: Path) -> None:
    stdout = _line({"reason": "build-finished", "success": 1})
    with pytest.raises(ClippyInvalidOutputError):
        _parse(stdout, tmp_path)


def test_a_broken_line_beside_a_successful_finish_is_still_invalid_output(tmp_path: Path) -> None:
    """Nothing can be concluded from output that cannot be read, success marker included."""
    with pytest.raises(ClippyInvalidOutputError):
        _parse("\n".join([_line({"reason": 7}), _FINISHED_OK]), tmp_path)


def test_a_nonzero_exit_with_a_successful_finish_is_execution_failed(tmp_path: Path) -> None:
    """Neither contract implies the other, so both are required."""
    with pytest.raises(ClippyFailedError):
        _parse(_FINISHED_OK, tmp_path, code=1)


def test_a_failed_build_quotes_the_error_level_rendered_text_before_the_warnings(tmp_path: Path) -> None:
    """Discarding non-warnings early loses exactly the lines a reader needs.

    Correction 1: the brief's version of this test only checked that "E0308" appears
    somewhere in the detail, which is true of any string containing it and pins nothing.
    This asserts the actual ordering claim: the error's rendered text is quoted at a lower
    index than the warning's, using two texts distinguishable from one another.
    """
    stdout = "\n".join([_warning("src/lib.rs"), _error(rendered="error[E0308]: mismatched"), _FINISHED_BAD])
    with pytest.raises(ClippyFailedError) as caught:
        _parse(stdout, tmp_path, code=101)
    detail = caught.value.detail
    assert "E0308" in detail
    assert "needless return" in detail
    assert detail.index("E0308") < detail.index("needless return")


def test_a_failed_build_with_no_rendered_text_falls_back_to_stderr(tmp_path: Path) -> None:
    with pytest.raises(ClippyFailedError) as caught:
        _parse(_FINISHED_BAD, tmp_path, stderr="linker not found", code=101)
    assert "linker not found" in caught.value.detail


def test_a_failure_whose_errors_are_all_configured_out_drops_the_workspace(tmp_path: Path) -> None:
    """Ebpy measures one build configuration; code outside it is not a broken repository."""
    stdout = "\n".join([_error(configured_out=True), _FINISHED_BAD])
    result = _parse(stdout, tmp_path, code=101)
    assert result.cells == {}
    assert [s.root for s in result.unmeasured] == ["."]
    assert result.unmeasured[0].packages == (".",)


def test_one_error_without_the_note_makes_the_whole_build_a_real_failure(tmp_path: Path) -> None:
    stdout = "\n".join([_error(configured_out=True), _error(configured_out=False), _FINISHED_BAD])
    with pytest.raises(ClippyFailedError):
        _parse(stdout, tmp_path, code=101)


def test_a_spanless_error_is_not_counted_toward_the_configured_out_rule(tmp_path: Path) -> None:
    """Rust 1.79 emits `aborting due to N previous errors` on every failure, with no spans."""
    stdout = "\n".join(
        [_error(configured_out=True), _error(spans=False, configured_out=False), _FINISHED_BAD]
    )
    result = _parse(stdout, tmp_path, code=101)
    assert len(result.unmeasured) == 1


def test_a_compile_error_macro_is_a_real_failure_not_a_configuration_mismatch(tmp_path: Path) -> None:
    """compile_error! is distinguished from an item configured out, not conflated with it.

    Correction 2: the brief's version of this test was a verbatim duplicate of the one
    above (identical stdout, identical assertion), so it tested nothing new. This gives it
    a genuinely `compile_error!`-shaped message — level `error`, `code: None`, exactly one
    primary span, and no "configured out" child note at all (not even an unrelated one) —
    beside a message that *is* a configured-out error, and checks the two are told apart:
    the compile_error! alone is enough to make the whole build a real failure.
    """
    compile_error = _line(
        {
            "reason": "compiler-message",
            "message": {
                "level": "error",
                "message": "boom",
                "rendered": "error: boom",
                "code": None,
                "spans": [
                    {"is_primary": True, "file_name": "src/lib.rs", "line_start": 1, "column_start": 1}
                ],
                "children": [],
            },
        }
    )
    stdout = "\n".join([_error(configured_out=True), compile_error, _FINISHED_BAD])
    with pytest.raises(ClippyFailedError):
        _parse(stdout, tmp_path, code=101)


def test_broken_error_facts_do_not_downgrade_a_failure_to_invalid_output(tmp_path: Path) -> None:
    """These are read only once failure is certain; strictness there is a downgrade, not a check."""
    stdout = "\n".join(
        [
            _line(
                {
                    "reason": "compiler-message",
                    "message": {
                        "level": "error",
                        "message": "boom",
                        "code": None,
                        "spans": "not a list",
                        "children": 7,
                    },
                }
            ),
            _FINISHED_BAD,
        ]
    )
    with pytest.raises(ClippyFailedError) as caught:
        _parse(stdout, tmp_path, code=101)
    assert not isinstance(caught.value, ClippyInvalidOutputError)


def test_an_unknown_level_is_never_type_checked_further(tmp_path: Path) -> None:
    """Rustc documents that enumerated fields may gain values; strictness there is a time bomb."""
    stdout = "\n".join(
        [
            _line(
                {
                    "reason": "compiler-message",
                    "message": {"level": "failure-note", "message": "x", "code": 7, "spans": 9},
                }
            ),
            _FINISHED_OK,
        ]
    )
    assert _parse(stdout, tmp_path).cells == {}


def test_an_unknown_reason_is_ignored_rather_than_rejected(tmp_path: Path) -> None:
    stdout = "\n".join([_line({"reason": "future-cargo-message", "payload": 1}), _FINISHED_OK])
    assert _parse(stdout, tmp_path).cells == {}


def test_a_broken_code_object_without_a_primary_span_is_only_discarded(tmp_path: Path) -> None:
    """Checking a value that is never read makes a run fail for nothing."""
    stdout = "\n".join(
        [
            _line(
                {
                    "reason": "compiler-message",
                    "message": {"level": "warning", "message": "x", "code": {"code": 7}, "spans": []},
                }
            ),
            _FINISHED_OK,
        ]
    )
    assert _parse(stdout, tmp_path).cells == {}


def test_a_rule_code_containing_a_newline_is_invalid_output(tmp_path: Path) -> None:
    """qualify_rule raises ValueError on those, and a bare ValueError breaks the parser's contract."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    stdout = "\n".join([_warning("src/lib.rs", code="a\nb"), _FINISHED_OK])
    with pytest.raises(ClippyInvalidOutputError):
        _parse(stdout, tmp_path)


def test_the_lowest_primary_span_is_chosen_deterministically(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    for name in ("a.rs", "b.rs"):
        (tmp_path / "src" / name).write_text("pub fn f() {}\n", encoding="utf-8")
    stdout = "\n".join(
        [
            _line(
                {
                    "reason": "compiler-message",
                    "message": {
                        "level": "warning",
                        "message": "x",
                        "code": {"code": "clippy::x"},
                        "spans": [
                            {"is_primary": True, "file_name": "src/b.rs", "line_start": 2, "column_start": 1},
                            {"is_primary": True, "file_name": "src/a.rs", "line_start": 9, "column_start": 1},
                        ],
                    },
                }
            ),
            _FINISHED_OK,
        ]
    )
    assert set(_parse(stdout, tmp_path).cells) == {"src/a.rs"}


def test_a_path_that_cannot_be_placed_becomes_unattributed_not_invalid_output(tmp_path: Path) -> None:
    stdout = "\n".join([_warning("/etc/passwd.rs"), _FINISHED_OK])
    result = _parse(stdout, tmp_path)
    assert result.cells == {}
    assert [f.file for f in result.unattributed] == ["/etc/passwd.rs"]


def test_generated_code_is_dropped_even_when_its_out_dir_arrives_later(tmp_path: Path) -> None:
    """build-script-executed can follow the messages it explains; one pass loses them."""
    out = "/build/x-abc/out"
    stdout = "\n".join(
        [
            _warning(f"{out}/gen.rs"),
            _line({"reason": "build-script-executed", "out_dir": out}),
            _FINISHED_OK,
        ]
    )
    result = _parse(stdout, tmp_path)
    assert result.cells == {}
    assert result.unattributed == ()
