"""Where the Cargo workspaces are, according to cargo itself.

Guessing from file layout does not work. Cargo searches parent directories for a
`[workspace]`, and `package.workspace` can name a root anywhere — so the outermost
`Cargo.toml` inside a repository can belong to a workspace outside it, whose other members
then get linted and reported relative to a root ebpy has never seen. `cargo metadata`
reports that situation correctly, which is the only reason it can be refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from ebpy.models import UnmeasuredScope
from ebpy.repo.facts import list_all_files
from ebpy.util import run

from ._errors import ClippyFailedError, ClippyInvalidOutputError, ClippyNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterator

_MANIFEST = "Cargo.toml"
_TARGET_SEGMENT = "target"
# cargo writes this beside every registry package it unpacks. It claims provenance — "this is
# cargo's copy of a published crate" — and nothing about whether the crate builds. A
# first-party package carrying this file would be dropped silently; that assumption is the
# price of not linting dependencies, and it is written down rather than hidden.
_VENDOR_MARKER = ".cargo-checksum.json"


@dataclass(frozen=True)
class RustWorkspace:
    """A Cargo workspace inside this repository, as cargo itself reports it."""

    # Repository-relative, always inside the repository. "." for a root workspace.
    root: PurePosixPath
    # Absolute, as cargo reported it. Deliberately not checked for containment: cargo may
    # legitimately place build output outside the repository, and what lands in a ceiling is
    # a diagnostic path, not an artifact location.
    target_directory: Path
    # Member package directories, repository-relative, ascending. Captured here because this
    # is the only moment they are knowable: the parser receives a RustWorkspace and a repo
    # root, and nothing downstream can reconstruct them.
    packages: tuple[str, ...]


@dataclass(frozen=True)
class RustTopology:
    """What cargo could and could not resolve in this repository."""

    workspaces: tuple[RustWorkspace, ...]
    unmeasured: tuple[UnmeasuredScope, ...]


def _candidates(cwd: Path) -> list[str]:
    return sorted(
        file
        for file in list_all_files(cwd)
        if (parts := PurePosixPath(file).parts)
        and parts[-1] == _MANIFEST
        and _TARGET_SEGMENT not in parts[:-1]
    )


def _relative(path: Path, repo_root: Path) -> str:
    return PurePosixPath(path.relative_to(repo_root)).as_posix()


def _inside(path: Path, repo_root: Path) -> bool:
    try:
        path.relative_to(repo_root)
    except ValueError:
        return False
    return True


def _metadata(cwd: Path, extra: list[str]) -> dict[str, Any]:
    argv = ["cargo", "metadata", "--no-deps", "--format-version", "1", *extra]
    try:
        result = run(argv, cwd)
    except OSError as error:
        raise ClippyNotFoundError(
            "cargo could not be executed",
            detail=f"cargo could not be executed: {error}",
        ) from error
    if result.code != 0:
        headline = f"cargo metadata failed (exit {result.code})"
        stderr = result.stderr.strip()
        raise ClippyFailedError(headline, detail=f"{headline}:\n{stderr}" if stderr else headline)
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ClippyInvalidOutputError(f"cargo metadata produced unparseable output: {error}") from error
    if not isinstance(raw, dict):
        raise ClippyInvalidOutputError("cargo metadata produced JSON of an unexpected shape")
    return raw


def _absolute_field(raw: dict[str, Any], key: str) -> Path:
    value = raw.get(key)
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ClippyInvalidOutputError(f"cargo metadata's {key} is not an absolute path")
    return Path(value)


def _member_manifests(raw: dict[str, Any]) -> Iterator[Path]:
    """Yield each workspace member's manifest, matching opaque package IDs by exact equality.

    The IDs are never parsed. The mapping closes inside this one document, so equality is
    all it takes, and a syntax the specification does not require ebpy to read is a syntax
    ebpy does not write a parser for.
    """
    members = raw.get("workspace_members")
    packages = raw.get("packages")
    if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
        raise ClippyInvalidOutputError("cargo metadata's workspace_members is not a list of strings")
    if not isinstance(packages, list):
        raise ClippyInvalidOutputError("cargo metadata's packages is not a list")
    by_id: dict[str, Path] = {}
    for package in packages:
        if not isinstance(package, dict):
            raise ClippyInvalidOutputError("cargo metadata reported a package of an unexpected shape")
        identifier = package.get("id")
        manifest = package.get("manifest_path")
        if not isinstance(identifier, str) or not isinstance(manifest, str):
            raise ClippyInvalidOutputError("cargo metadata reported a package without an id or manifest")
        if not Path(manifest).is_absolute():
            raise ClippyInvalidOutputError("cargo metadata reported a relative manifest_path")
        if identifier in by_id:
            raise ClippyInvalidOutputError(f"cargo metadata reported package id {identifier!r} twice")
        by_id[identifier] = Path(manifest)
    for member in members:
        if member not in by_id:
            raise ClippyInvalidOutputError(f"cargo metadata's member {member!r} matches no package")
        yield by_id[member]


def _resolve(manifest: Path, repo_root: Path) -> tuple[RustWorkspace, list[Path]]:
    """Resolve one candidate manifest into its workspace, plus the manifests now handled.

    Two invocations, because `--manifest-path` does not move the directory cargo and rustup
    search from: a nested workspace's `rust-toolchain.toml` and `.cargo/config.toml` are only
    seen from inside it. `[1]` answers "which workspace does this manifest belong to"; `[2]`
    re-reads from that root so the adopted `target_directory` is the one the measuring cwd
    will see. `[1]` failing is never retried from the root — resolving it there would produce
    a measurement whose subject nobody could name.
    """
    first = _metadata(manifest.parent, ["--manifest-path", str(manifest)])
    root = _absolute_field(first, "workspace_root").resolve()
    if not _inside(root, repo_root):
        raise ClippyInvalidOutputError(
            f"{_display(manifest, repo_root)} belongs to a Cargo workspace outside this repository"
        )
    second = _metadata(root, [])
    if _absolute_field(second, "workspace_root").resolve() != root:
        raise ClippyInvalidOutputError("cargo metadata reported two different workspace roots")

    member_manifests = [path.resolve() for path in _member_manifests(second)]
    for member in member_manifests:
        if not _inside(member, repo_root):
            raise ClippyInvalidOutputError(
                f"the workspace at {_relative(root, repo_root)} has a member outside this repository"
            )

    workspace = RustWorkspace(
        root=PurePosixPath(_relative(root, repo_root)),
        target_directory=_absolute_field(second, "target_directory"),
        packages=tuple(sorted(_relative(member.parent, repo_root) for member in member_manifests)),
    )
    # The candidate itself and the root manifest are marked alongside the members: a virtual
    # workspace's root has no [package], so it appears in neither workspace_members nor
    # packages, and marking members alone leaves it to be probed again forever.
    return workspace, [manifest, (root / _MANIFEST).resolve(), *member_manifests]


def _display(manifest: Path, repo_root: Path) -> str:
    return _relative(manifest, repo_root) if _inside(manifest, repo_root) else manifest.name


def rust_topology(cwd: Path) -> RustTopology:
    """Resolve this repository into the Cargo workspaces ebpy can measure.

    Candidates cargo cannot resolve are reported in `unmeasured` rather than raised, so one
    checked-in vendored manifest cannot make a healthy repository unmeasurable. Every
    candidate failing is still a failure: "dropped them all" and "measured zero" are
    different facts, and the second one would let `prune` empty the ceiling.

    Raises:
        ClippyNotFoundError: cargo cannot be executed.
        ClippyFailedError: no candidate resolved.
        ClippyInvalidOutputError: metadata output cannot be interpreted safely.

    """
    repo_root = cwd.resolve()
    workspaces: dict[str, RustWorkspace] = {}
    unmeasured: list[UnmeasuredScope] = []
    handled: set[Path] = set()
    first_failure: ClippyFailedError | None = None

    for candidate in _candidates(cwd):
        manifest = (cwd / candidate).resolve()
        if manifest in handled:
            continue
        # Consulted only for a candidate no workspace claimed: members are already handled by
        # now, so a first-party member carrying the marker cannot be dropped here.
        if (manifest.parent / _VENDOR_MARKER).is_file():
            handled.add(manifest)
            continue
        try:
            workspace, resolved = _resolve(manifest, repo_root)
        except ClippyInvalidOutputError:
            raise
        except ClippyFailedError as error:
            handled.add(manifest)
            directory = str(PurePosixPath(candidate).parent)
            unmeasured.append(UnmeasuredScope(root=directory, packages=(directory,)))
            first_failure = first_failure or error
            continue
        handled.update(resolved)
        workspaces.setdefault(workspace.root.as_posix(), workspace)

    if not workspaces and first_failure is not None:
        raise first_failure
    return RustTopology(
        workspaces=tuple(workspaces[key] for key in sorted(workspaces)),
        unmeasured=tuple(unmeasured),
    )
