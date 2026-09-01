"""Probing, invoking and aggregating clippy across a repository's workspaces."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import pytest

import ebpy.tools.clippy as clippy_package
from ebpy.measurement import Failed, Unavailable
from ebpy.models import UnmeasuredScope
from ebpy.tools.clippy import _runner
from ebpy.tools.clippy._errors import ClippyFailedError, ClippyNotFoundError, ClippyNoWorkspaceError
from ebpy.tools.clippy._runner import run_clippy_check
from ebpy.tools.clippy._topology import RustTopology, RustWorkspace
from ebpy.tools.clippy.analyzer import ClippyAnalyzer
from ebpy.util import ExecResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from ebpy.models import AnalysisMeasurement

_VERSION_OK = ExecResult(code=0, stdout="clippy 0.1.96 (abc 2026-05-25)\n", stderr="")
_FINISHED_OK = json.dumps({"reason": "build-finished", "success": True})


def _workspace(root: str) -> RustWorkspace:
    return RustWorkspace(root=PurePosixPath(root), target_directory=Path("/t"), packages=(root,))


def _install(
    monkeypatch: pytest.MonkeyPatch,
    topology: RustTopology,
    responder: Callable[[list[str], Path], ExecResult],
) -> None:
    monkeypatch.setattr(_runner, "rust_topology", lambda _cwd: topology)
    monkeypatch.setattr(_runner, "run", responder)


def test_a_repository_with_no_workspace_has_nothing_for_clippy_to_run_against(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, RustTopology((), ()), lambda _a, _c: _VERSION_OK)
    with pytest.raises(ClippyNoWorkspaceError):
        run_clippy_check(tmp_path)


def test_an_aliased_cargo_clippy_that_does_not_name_itself_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cargo alias shadows the external subcommand and still exits 0; the name is the tell."""
    _install(
        monkeypatch,
        RustTopology((_workspace("."),), ()),
        lambda _a, _c: ExecResult(code=0, stdout="", stderr="warning: user-defined alias"),
    )
    with pytest.raises(ClippyNotFoundError):
        run_clippy_check(tmp_path)


def test_a_missing_cargo_during_the_probe_is_unavailable_not_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`docs/measurement-seam.md` puts executable-not-found on the Unavailable side."""

    def _boom(_argv: list[str], _cwd: Path) -> ExecResult:
        raise FileNotFoundError("cargo")

    _install(monkeypatch, RustTopology((_workspace("."),), ()), _boom)
    with pytest.raises(ClippyNotFoundError):
        run_clippy_check(tmp_path)


def test_every_workspace_is_probed_before_any_is_compiled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise a full build finishes before the second probe reports the component missing."""
    calls: list[str] = []

    def _respond(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv[2])
        if argv[2] == "--version":
            return _VERSION_OK if len(calls) == 1 else ExecResult(code=1, stdout="", stderr="no clippy")
        return ExecResult(code=0, stdout=_FINISHED_OK, stderr="")

    _install(monkeypatch, RustTopology((_workspace("a"), _workspace("b")), ()), _respond)
    with pytest.raises(ClippyNotFoundError):
        run_clippy_check(tmp_path)
    assert "--workspace" not in calls


def test_the_measurement_command_carries_every_required_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []

    def _respond(argv: list[str], _cwd: Path) -> ExecResult:
        seen.append(argv)
        if "--version" in argv:
            return _VERSION_OK
        return ExecResult(code=0, stdout=_FINISHED_OK, stderr="")

    _install(monkeypatch, RustTopology((_workspace("."),), ()), _respond)
    run_clippy_check(tmp_path)
    measure = seen[-1]
    assert "--workspace" in measure
    assert "--message-format=json" in measure
    assert measure[measure.index("--target-dir") + 1].endswith("ebpy-clippy")
    assert measure[-3:] == ["--", "--cap-lints", "warn"]


def test_one_workspace_failing_makes_the_whole_measurement_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial success as Measured would put the failed workspace's cells in as zero."""

    def _respond(argv: list[str], cwd: Path) -> ExecResult:
        if "--version" in argv:
            return _VERSION_OK
        if cwd.name == "b":
            return ExecResult(code=101, stdout="", stderr="broken")
        return ExecResult(code=0, stdout=_FINISHED_OK, stderr="")

    _install(monkeypatch, RustTopology((_workspace("a"), _workspace("b")), ()), _respond)
    with pytest.raises(ClippyFailedError) as caught:
        run_clippy_check(tmp_path)
    assert "b" in caught.value.detail


def test_cells_from_two_workspaces_are_added_rather_than_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`merge_cells` raises on a repeated file x rule; two workspaces may compile one .rs.

    Fixture note (deviates from the task brief as written): under workspace root ``side``,
    a reported ``shared/lib.rs`` would prefix to ``side/shared/lib.rs``, which this fixture
    never creates, so `attribute_path` would refuse it and the count would be 1, not 2. A
    real relative `path` dependency reports a path relative to *its own* workspace root, so
    the ``side`` workspace's diagnostic is made to say ``../shared/lib.rs`` instead — which
    prefixes to ``side/../shared/lib.rs``, collapses to ``shared/lib.rs``, and matches the
    root workspace's own contribution to the same cell.
    """
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")

    def _warning(file_name: str) -> str:
        return json.dumps(
            {
                "reason": "compiler-message",
                "message": {
                    "level": "warning",
                    "message": "x",
                    "code": {"code": "clippy::x"},
                    "spans": [
                        {
                            "is_primary": True,
                            "file_name": file_name,
                            "line_start": 1,
                            "column_start": 1,
                        }
                    ],
                },
            }
        )

    def _respond(argv: list[str], cwd: Path) -> ExecResult:
        if "--version" in argv:
            return _VERSION_OK
        file_name = "../shared/lib.rs" if cwd.name == "side" else "shared/lib.rs"
        return ExecResult(code=0, stdout="\n".join([_warning(file_name), _FINISHED_OK]), stderr="")

    _install(monkeypatch, RustTopology((_workspace("."), _workspace("side")), ()), _respond)
    result = run_clippy_check(tmp_path)
    assert result.cells["shared/lib.rs"]["clippy:clippy::x"] == 2


def test_the_topology_unmeasured_scopes_reach_the_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dropped = UnmeasuredScope(root="vendor/dep", packages=("vendor/dep",))

    def _respond(argv: list[str], _cwd: Path) -> ExecResult:
        return _VERSION_OK if "--version" in argv else ExecResult(code=0, stdout=_FINISHED_OK, stderr="")

    _install(monkeypatch, RustTopology((_workspace("."),), (dropped,)), _respond)
    assert run_clippy_check(tmp_path).unmeasured == (dropped,)


def test_the_analyzer_turns_each_error_into_the_right_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single except clause collapsing these three destroys every message a reader can act on."""
    cases = {
        ClippyNotFoundError("no cargo"): Unavailable,
        ClippyFailedError("broken"): Failed,
    }
    for error, expected in cases.items():

        def _raise(_cwd: Path, _error: BaseException = error) -> AnalysisMeasurement:
            raise _error

        monkeypatch.setattr(clippy_package, "run_clippy_check", _raise)
        assert isinstance(ClippyAnalyzer().measure(tmp_path), expected)


def test_the_analyzer_names_its_language_and_what_it_finds() -> None:
    """'Clippy lints' would be too narrow: rustc's own lints share this stream and get cells."""
    analyzer = ClippyAnalyzer()
    assert analyzer.name == "clippy"
    assert analyzer.language == "rust"
    assert analyzer.noun == "Rust lint warnings"


def _clippy_available() -> bool:
    if shutil.which("cargo") is None:
        return False
    probe = subprocess.run(["cargo", "clippy", "--version"], capture_output=True, text=True, check=False)
    return probe.returncode == 0 and probe.stdout.startswith("clippy ")


needs_clippy = pytest.mark.skipif(
    not _clippy_available(), reason="needs a toolchain whose `cargo clippy --version` succeeds"
)

_CRATE = "[package]\nname='{name}'\nversion='0.1.0'\nedition='2021'\n"
# `needless_return` is one of clippy's oldest and most stable lints; using a recent one would
# make the expected count depend on the toolchain rather than on the code.
_DIRTY = "pub fn f() -> i32 {\n    return 1;\n}\n"


def _crate(root: Path, name: str, body: str = _DIRTY) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(_CRATE.format(name=name), encoding="utf-8")
    (root / "src" / "lib.rs").write_text(body, encoding="utf-8")


@needs_clippy
def test_a_non_virtual_workspace_measures_every_member(tmp_path: Path) -> None:
    """Without --workspace, cargo builds only the root package and members enter as zero."""
    _crate(tmp_path, "root")
    (tmp_path / "Cargo.toml").write_text(
        _CRATE.format(name="root") + "\n[workspace]\nmembers=['crates/a']\n", encoding="utf-8"
    )
    _crate(tmp_path / "crates" / "a", "a")
    result = run_clippy_check(tmp_path)
    assert set(result.cells) == {"src/lib.rs", "crates/a/src/lib.rs"}


@needs_clippy
def test_a_repository_that_denies_all_clippy_lints_can_still_be_measured(tmp_path: Path) -> None:
    """`--cap-lints warn` is what lets Clippy's own recommended CI setup be frozen at all."""
    _crate(tmp_path, "a")
    (tmp_path / "Cargo.toml").write_text(
        _CRATE.format(name="a") + "\n[lints.clippy]\nall = 'deny'\n", encoding="utf-8"
    )
    result = run_clippy_check(tmp_path)
    assert result.cells["src/lib.rs"]["clippy:clippy::needless_return"] == 1


@needs_clippy
def test_a_cfg_hidden_module_drops_its_workspace_instead_of_failing_the_run(tmp_path: Path) -> None:
    _crate(
        tmp_path,
        "a",
        body="#[cfg(fuzzing)]\npub mod fuzz;\n\npub fn use_it() { crate::fuzz::f(); }\n",
    )
    result = run_clippy_check(tmp_path)
    assert result.cells == {}
    assert [s.root for s in result.unmeasured] == ["."]


@needs_clippy
def test_a_misspelled_module_is_a_real_failure_and_is_never_dropped(tmp_path: Path) -> None:
    """A typo produces the same E0433 as a cfg-hidden module; only the note tells them apart."""
    _crate(tmp_path, "a", body="pub fn use_it() { crate::nosuch::f(); }\n")
    with pytest.raises(ClippyFailedError):
        run_clippy_check(tmp_path)


@needs_clippy
def test_a_type_error_is_a_real_failure(tmp_path: Path) -> None:
    _crate(tmp_path, "a", body='pub fn f() -> i32 { "x" }\n')
    with pytest.raises(ClippyFailedError):
        run_clippy_check(tmp_path)


@needs_clippy
def test_a_compile_error_macro_beside_a_cfg_failure_is_a_real_failure(tmp_path: Path) -> None:
    """`compile_error!` has code: None; a code-based rule would drop it on 1.79 and 1.85."""
    _crate(
        tmp_path,
        "a",
        body=(
            "#[cfg(fuzzing)]\npub mod fuzz;\n"
            "pub fn use_it() { crate::fuzz::f(); }\n"
            'compile_error!("select a backend");\n'
        ),
    )
    with pytest.raises(ClippyFailedError):
        run_clippy_check(tmp_path)


@needs_clippy
def test_a_remapped_path_produces_no_cells_and_leaves_the_run_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The remap rewrites the path textually and still exits 0 with success=true."""
    _crate(tmp_path, "a")
    monkeypatch.setenv("RUSTFLAGS", "--remap-path-prefix=src=shadow")
    result = run_clippy_check(tmp_path)
    assert result.cells == {}
    assert result.unattributed


@needs_clippy
def test_build_script_output_is_dropped_and_the_measurement_still_succeeds(tmp_path: Path) -> None:
    """Treating generated code as unattributed would make freeze refuse this repository forever."""
    _crate(tmp_path, "gendemo", body='include!(concat!(env!("OUT_DIR"), "/gen.rs"));\n')
    (tmp_path / "build.rs").write_text(
        "use std::{env, fs, path::Path};\n"
        "fn main() {\n"
        '    let out = env::var("OUT_DIR").unwrap();\n'
        '    fs::write(Path::new(&out).join("gen.rs"), '
        '"pub fn g() -> i32 { return 1; }\\n").unwrap();\n'
        "}\n",
        encoding="utf-8",
    )
    result = run_clippy_check(tmp_path)
    assert result.unattributed == ()
