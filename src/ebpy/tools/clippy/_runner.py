"""Running clippy across every Cargo workspace this repository holds.

Probe, then measure, then aggregate — with the probe finished for every workspace before the
first compile starts, so a missing clippy component is reported before an hour of building
rather than after it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ebpy.models import AnalysisMeasurement, CellCounts, UnattributedFinding, UnmeasuredScope
from ebpy.util import run

from ._errors import ClippyFailedError, ClippyNotFoundError, ClippyNoWorkspaceError
from ._parser import parse_clippy_output
from ._topology import RustWorkspace, rust_topology

if TYPE_CHECKING:
    from pathlib import Path

# Kept apart from the developer's own cache. The extra rustc argument below enters cargo's
# fingerprint, so sharing one target directory makes ebpy's runs and a hand-run
# `cargo clippy` invalidate each other, turning every alternation into a full rebuild. It sits
# *under* the directory cargo reported so `cargo clean` and the existing .gitignore still cover it.
_TARGET_SUBDIR = "ebpy-clippy"

_INSTALL_HINT = (
    "cargo or the clippy component could not be run here. On a rustup-managed toolchain, "
    "`rustup component add clippy` installs it."
)


def _workspace_dir(repo_root: Path, workspace: RustWorkspace) -> Path:
    root = workspace.root.as_posix()
    return repo_root if root == "." else repo_root / root


def _probe(directory: Path) -> None:
    """Confirm a real `cargo clippy` answers in this workspace's directory.

    Per workspace, because rustup resolves the toolchain from the current directory: a nested
    `rust-toolchain.toml` means a probe at the repository root measured a different toolchain
    than the one that will actually run.

    The exit code alone is not enough. `cargo clippy` is an external subcommand and a cargo
    alias can shadow it — cargo warns and carries on with exit 0. A real clippy names itself,
    so the opening of stdout is what is checked. That is a measured behaviour rather than a
    documented one, which is why the integration tests run at both ends of the support range.
    The warning's wording is deliberately not read: it is documented as becoming a hard error,
    at which point the non-zero exit catches it anyway.
    """
    try:
        result = run(["cargo", "clippy", "--version"], directory)
    except OSError as error:
        # Converted here rather than caught in the analyzer: `util.run` calls subprocess
        # directly, so a missing executable raises, and mypy's `except OSError -> Failed` is
        # only correct there because `find_mypy` proved the executable exists first.
        raise ClippyNotFoundError(_INSTALL_HINT, detail=f"{_INSTALL_HINT}\n{error}") from error
    if result.code != 0 or not result.stdout.startswith("clippy "):
        detail = "\n".join([_INSTALL_HINT, result.stderr.strip()]).strip()
        raise ClippyNotFoundError(_INSTALL_HINT, detail=detail)


def _measure_workspace(directory: Path, workspace: RustWorkspace, repo_root: Path) -> AnalysisMeasurement:
    argv = [
        "cargo",
        "clippy",
        # Without it, a non-virtual workspace builds only the root package or `default-members`.
        # The rest vanish silently, enter the ceiling as zero, and the next prune lowers it wrongly.
        "--workspace",
        "--message-format=json",
        "--target-dir",
        str(workspace.target_directory / _TARGET_SUBDIR),
        "--",
        # `[lints.clippy] all = "deny"`, `#![deny(...)]` and `RUSTFLAGS=-Dwarnings` all promote
        # lints to errors and set `success: false`, so a repository following Clippy's own CI
        # guide could never freeze. This caps lint *levels* only; E0308 stays an error.
        "--cap-lints",
        "warn",
    ]
    result = run(argv, directory)
    return parse_clippy_output(
        result.stdout, result.stderr, result.code, workspace=workspace, repo_root=repo_root
    )


def run_clippy_check(cwd: Path) -> AnalysisMeasurement:
    """Measure every Cargo workspace in this repository as one value.

    One workspace failing fails the whole measurement: reporting partial success as Measured
    would enter the failed workspace's cells as zero, and `prune` would then lower a ceiling
    nobody re-measured.
    """
    repo_root = cwd.resolve()
    topology = rust_topology(cwd)
    if not topology.workspaces:
        raise ClippyNoWorkspaceError(
            "no Cargo workspace in this repository",
            detail=(
                "cargo resolved no workspace here, so clippy has nothing to measure. If no "
                "Cargo.toml here is meant to be a crate ebpy measures, declare the analyzers "
                "you do want ratcheted in .ebpy/config.json to take clippy out of scope."
            ),
        )

    # Ascending by repository-relative root, never by the order metadata happened to run:
    # candidate order comes from `git ls-files`, and a message should not change wording
    # because git's output order changed.
    ordered = sorted(topology.workspaces, key=lambda workspace: workspace.root.as_posix())
    for workspace in ordered:
        _probe(_workspace_dir(repo_root, workspace))

    cells: CellCounts = {}
    unattributed: list[UnattributedFinding] = []
    unmeasured: list[UnmeasuredScope] = list(topology.unmeasured)
    for workspace in ordered:
        root = workspace.root.as_posix()
        try:
            part = _measure_workspace(_workspace_dir(repo_root, workspace), workspace, repo_root)
        except ClippyFailedError as error:
            raise type(error)(f"{root}: {error.summary}", detail=f"{root}:\n{error.detail}") from error
        for file, rules in part.cells.items():
            target = cells.setdefault(file, {})
            for rule, count in rules.items():
                # Added, not rejected: `merge_cells` forbids a repeated file x rule because
                # namespacing makes it impossible *across analyzers*, but two workspaces of
                # one analyzer may legitimately compile the same .rs via a relative `path`.
                # A count is what this measurement observed, and it reproduces.
                target[rule] = target.get(rule, 0) + count
        unattributed.extend(part.unattributed)
        unmeasured.extend(part.unmeasured)

    return AnalysisMeasurement(cells=cells, unattributed=tuple(unattributed), unmeasured=tuple(unmeasured))
