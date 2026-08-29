"""Cargo workspace discovery: what cargo could and could not resolve in this repository."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from ebpy.tools.clippy import _topology
from ebpy.tools.clippy._errors import ClippyFailedError, ClippyInvalidOutputError, ClippyNotFoundError
from ebpy.tools.clippy._topology import rust_topology
from ebpy.util import ExecResult

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _metadata(root: Path, members: list[Path]) -> str:
    return json.dumps(
        {
            "workspace_root": str(root),
            "target_directory": str(root / "target"),
            "workspace_members": [f"path+file://{m}#0.1.0" for m in members],
            "packages": [
                {"id": f"path+file://{m}#0.1.0", "manifest_path": str(m / "Cargo.toml")} for m in members
            ],
        }
    )


def _fake_run(responses: dict[str, ExecResult]) -> Callable[[list[str], Path], ExecResult]:
    def _run(argv: list[str], cwd: Path) -> ExecResult:
        del argv
        return responses[str(cwd)]

    return _run


def test_a_single_package_repository_resolves_to_one_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    root = tmp_path.resolve()
    ok = ExecResult(code=0, stdout=_metadata(root, [root]), stderr="")
    monkeypatch.setattr(_topology, "run", _fake_run({str(root): ok}))
    topology = rust_topology(tmp_path)
    assert [w.root.as_posix() for w in topology.workspaces] == ["."]
    assert topology.workspaces[0].packages == (".",)
    assert topology.unmeasured == ()


def test_a_workspace_root_outside_the_repository_is_invalid_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository manifest can be a member of an outside workspace; that must be named, not measured."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    outside = tmp_path.parent.resolve() / "elsewhere"
    payload = _metadata(outside, [outside])
    monkeypatch.setattr(_topology, "run", lambda _argv, _cwd: ExecResult(code=0, stdout=payload, stderr=""))
    with pytest.raises(ClippyInvalidOutputError):
        rust_topology(tmp_path)


def test_a_member_outside_the_repository_is_invalid_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`package.workspace` lets cargo accept a member above the root; clippy then reports it absolute."""
    (tmp_path / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    root = tmp_path.resolve()
    outside = root.parent / "sibling"
    payload = _metadata(root, [outside])
    monkeypatch.setattr(_topology, "run", lambda _argv, _cwd: ExecResult(code=0, stdout=payload, stderr=""))
    with pytest.raises(ClippyInvalidOutputError):
        rust_topology(tmp_path)


def test_a_candidate_cargo_cannot_resolve_is_dropped_rather_than_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checked-in vendor/ makes metadata exit 101 while the repository itself builds fine."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    (tmp_path / "vendor" / "dep").mkdir(parents=True)
    (tmp_path / "vendor" / "dep" / "Cargo.toml").write_text("[package]\nname='d'\n", encoding="utf-8")
    root = tmp_path.resolve()
    ok = ExecResult(code=0, stdout=_metadata(root, [root]), stderr="")
    bad = ExecResult(code=101, stdout="", stderr="not in a workspace")
    monkeypatch.setattr(_topology, "run", _fake_run({str(root): ok, str(root / "vendor" / "dep"): bad}))
    topology = rust_topology(tmp_path)
    assert len(topology.workspaces) == 1
    assert [s.root for s in topology.unmeasured] == ["vendor/dep"]
    assert topology.unmeasured[0].packages == ("vendor/dep",)


def test_every_candidate_failing_is_a_failure_not_an_empty_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping everything must not become Measured(cells={}), which prune would act on."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    bad = ExecResult(code=101, stdout="", stderr="broken manifest")
    monkeypatch.setattr(_topology, "run", lambda _argv, _cwd: bad)
    with pytest.raises(ClippyFailedError):
        rust_topology(tmp_path)


def test_a_vendored_candidate_is_never_a_candidate_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A vendored dependency is not fixable code; giving it a ceiling would be pointless.

    It is skipped rather than recorded as unmeasured: recording it would grow the contract's
    set every time `cargo vendor` adds a dependency, and every growth reads as a regression.
    """
    (tmp_path / "Cargo.toml").write_text("[workspace]\nexclude=['vendor']\n", encoding="utf-8")
    dep = tmp_path / "vendor" / "cfg-if"
    dep.mkdir(parents=True)
    (dep / "Cargo.toml").write_text("[package]\nname='cfg-if'\n", encoding="utf-8")
    (dep / ".cargo-checksum.json").write_text("{}", encoding="utf-8")
    root = tmp_path.resolve()
    ok = ExecResult(code=0, stdout=_metadata(root, []), stderr="")
    monkeypatch.setattr(_topology, "run", _fake_run({str(root): ok}))
    topology = rust_topology(tmp_path)
    assert len(topology.workspaces) == 1
    assert topology.unmeasured == ()


def test_a_workspace_member_is_never_tested_for_the_vendor_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Members are already handled by the time the marker is consulted, so one cannot vanish."""
    (tmp_path / "Cargo.toml").write_text("[workspace]\nmembers=['a']\n", encoding="utf-8")
    member = tmp_path / "a"
    member.mkdir()
    (member / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    (member / ".cargo-checksum.json").write_text("{}", encoding="utf-8")
    root = tmp_path.resolve()
    ok = ExecResult(code=0, stdout=_metadata(root, [root / "a"]), stderr="")
    monkeypatch.setattr(_topology, "run", _fake_run({str(root): ok}))
    topology = rust_topology(tmp_path)
    assert topology.workspaces[0].packages == ("a",)


def test_a_missing_cargo_executable_is_reported_as_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")

    def _boom(_argv: list[str], _cwd: Path) -> ExecResult:
        raise FileNotFoundError("cargo")

    monkeypatch.setattr(_topology, "run", _boom)
    with pytest.raises(ClippyNotFoundError):
        rust_topology(tmp_path)


def test_unreadable_metadata_output_is_invalid_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful cargo whose output ebpy cannot read says nothing about the repository."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    monkeypatch.setattr(
        _topology, "run", lambda _argv, _cwd: ExecResult(code=0, stdout="not json", stderr="")
    )
    with pytest.raises(ClippyInvalidOutputError):
        rust_topology(tmp_path)


def test_a_repository_with_no_manifests_resolves_to_no_workspaces(tmp_path: Path) -> None:
    assert rust_topology(tmp_path).workspaces == ()


def _clippy_available() -> bool:
    if shutil.which("cargo") is None:
        return False
    probe = subprocess.run(["cargo", "clippy", "--version"], capture_output=True, text=True, check=False)
    return probe.returncode == 0 and probe.stdout.startswith("clippy ")


needs_clippy = pytest.mark.skipif(
    not _clippy_available(), reason="needs a toolchain whose `cargo clippy --version` succeeds"
)


@needs_clippy
def test_a_nested_manifest_resolves_against_real_cargo(tmp_path: Path) -> None:
    """The candidate must reach cargo absolute; relative would make it look for crates/a/crates/a."""
    (tmp_path / "Cargo.toml").write_text("[workspace]\nmembers=['crates/a']\n", encoding="utf-8")
    crate = tmp_path / "crates" / "a"
    (crate / "src").mkdir(parents=True)
    (crate / "Cargo.toml").write_text(
        "[package]\nname='a'\nversion='0.1.0'\nedition='2021'\n", encoding="utf-8"
    )
    (crate / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    topology = rust_topology(tmp_path)
    assert [w.root.as_posix() for w in topology.workspaces] == ["."]
    assert topology.workspaces[0].packages == ("crates/a",)


@needs_clippy
def test_a_virtual_workspace_root_is_marked_handled_and_not_probed_twice(tmp_path: Path) -> None:
    """A virtual root appears in neither workspace_members nor packages, so it needs marking."""
    (tmp_path / "Cargo.toml").write_text("[workspace]\nmembers=['a']\nresolver='2'\n", encoding="utf-8")
    crate = tmp_path / "a"
    (crate / "src").mkdir(parents=True)
    (crate / "Cargo.toml").write_text(
        "[package]\nname='a'\nversion='0.1.0'\nedition='2021'\n", encoding="utf-8"
    )
    (crate / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    topology = rust_topology(tmp_path)
    assert len(topology.workspaces) == 1


@needs_clippy
def test_an_excluded_package_is_found_as_its_own_workspace(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        "[workspace]\nmembers=['a']\nexclude=['side']\nresolver='2'\n", encoding="utf-8"
    )
    for name in ("a", "side"):
        crate = tmp_path / name
        (crate / "src").mkdir(parents=True)
        (crate / "Cargo.toml").write_text(
            f"[package]\nname='{name}'\nversion='0.1.0'\nedition='2021'\n", encoding="utf-8"
        )
        (crate / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    roots = {w.root.as_posix() for w in rust_topology(tmp_path).workspaces}
    assert roots == {".", "side"}


@needs_clippy
def test_a_checked_in_vendor_directory_does_not_make_the_repository_unmeasurable(tmp_path: Path) -> None:
    """`cargo metadata` exits 101 for a non-excluded vendored manifest; the root is still fine.

    The 101 only happens when an ancestor manifest declares `[workspace]`: cargo's ancestor
    search for a workspace root skips any Cargo.toml that lacks that table, so a root with
    only `[package]` would let `vendor/dep` resolve as its own implicit one-crate workspace
    instead — a different, unmeasurable-repository-only scenario this test does not want.
    """
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname='a'\nversion='0.1.0'\nedition='2021'\n\n[workspace]\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    dep = tmp_path / "vendor" / "dep"
    (dep / "src").mkdir(parents=True)
    (dep / "Cargo.toml").write_text(
        "[package]\nname='dep'\nversion='0.1.0'\nedition='2021'\n", encoding="utf-8"
    )
    (dep / "src" / "lib.rs").write_text("pub fn g() {}\n", encoding="utf-8")
    topology = rust_topology(tmp_path)
    assert [w.root.as_posix() for w in topology.workspaces] == ["."]
    assert [s.root for s in topology.unmeasured] == ["vendor/dep"]
