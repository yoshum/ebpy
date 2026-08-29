"""Placing a reported clippy path in the ceiling's coordinate system, or refusing to.

Three outcomes and never a fourth: a cell, a generated file to drop, or a finding that
cannot be attributed. Every reason a path cannot be placed — a UNC share, a drive-relative
spelling, a NUL byte, a symlink loop, a `--remap-path-prefix` target that does not exist —
reaches the same conclusion, because the ratchet's question is only ever "can this be a
coordinate", never "why not".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Literal

from ebpy.cell_key import normalize_analyzer_path

from ._errors import ClippyInvalidOutputError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


@dataclass(frozen=True)
class PathVerdict:
    """Where a reported diagnostic path goes: a cell, the generated-code bin, or unattributed."""

    kind: Literal["cell", "generated", "unattributed"]
    path: str = ""


_UNATTRIBUTED = PathVerdict("unattributed")
_GENERATED = PathVerdict("generated")


def _is_absolute(path: str) -> bool:
    """Judge absoluteness in both flavours, plus a bare drive.

    `C:/outside/file.rs` is not absolute to PurePosixPath, so one flavour would prefix it
    with the workspace root and let it pass as repository-relative. `C:foo.rs` is absolute
    in neither, and only its drive gives it away.
    """
    return (
        PurePosixPath(path).is_absolute()
        or PureWindowsPath(path).is_absolute()
        or bool(PureWindowsPath(path).drive)
    )


def _collapse(path: str, *, keep_leading_parent: bool) -> str | None:
    """Fold `.` and `..` lexically, never by resolving. None means a `..` escaped.

    Lexical because resolving depends on this host's symlinks, and a ceiling keyed on that
    would not reproduce on another machine. `PurePosixPath` will not do it — Python keeps
    `..` deliberately.
    """
    stack: list[str] = []
    for part in path.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif keep_leading_parent:
                stack.append("..")
            else:
                return None
            continue
        stack.append(part)
    return "/".join(stack)


def normalize_out_dir(raw: str) -> str:
    """Normalize a reported `out_dir` into the spelling a diagnostic path can be compared against."""
    slashed = raw.replace("\\", "/")
    if not _is_absolute(slashed):
        raise ClippyInvalidOutputError(f"cargo reported a relative build-script out_dir: {raw!r}")
    drive = PureWindowsPath(slashed).drive
    rest = slashed[len(drive) :]
    rooted = rest.startswith("/")
    body = _collapse(rest, keep_leading_parent=True) or ""
    return f"{drive}{'/' if rooted else ''}{body}".rstrip("/")


def _under_out_dir(path: str, out_dirs: Sequence[str]) -> bool:
    candidate = path.rstrip("/")
    return any(candidate == out or candidate.startswith(f"{out}/") for out in out_dirs)


def _is_repository_file(repo_root: Path, relative: str) -> bool:
    """Confirm the path names a real file that resolves inside the repository.

    Without this, `--remap-path-prefix=src=shadow` — which rewrites diagnostic paths textually
    while still exiting 0 with `success=true` — puts cells for files that do not exist into
    the ceiling. Every filesystem error is an answer of "no": clippy's output is external
    input, and the parser's contract is that only its two error types leave it.
    """
    try:
        root = repo_root.resolve()
        candidate = (root / relative).resolve()
        if not candidate.is_file():
            return False
        candidate.relative_to(root)
    except (OSError, ValueError, RuntimeError):
        return False
    return True


def attribute_path(
    reported: str, *, workspace_root: str, repo_root: Path, out_dirs: Sequence[str]
) -> PathVerdict:
    """Decide where one reported diagnostic path belongs.

    `workspace_root` is repository-relative and comes from `cargo metadata`, not from the
    candidate manifest's directory: clippy reports relative to the workspace root, and those
    two differ for every nested workspace.
    """
    slashed = reported.replace("\\", "/")
    if _is_absolute(slashed):
        return _GENERATED if _under_out_dir(slashed, out_dirs) else _UNATTRIBUTED

    collapsed = _collapse(slashed, keep_leading_parent=True)
    # Emptiness alone is not enough: `..` and `../foo/..` both collapse to `..`, and prefixing
    # `crates/a` onto that yields the directory `crates`, which would become a cell key.
    if not collapsed or collapsed.split("/")[-1] == "..":
        return _UNATTRIBUTED

    prefixed = f"{workspace_root}/{collapsed}" if workspace_root not in {"", "."} else collapsed
    final = _collapse(prefixed, keep_leading_parent=False)
    if not final or not _is_repository_file(repo_root, final):
        return _UNATTRIBUTED
    return PathVerdict("cell", normalize_analyzer_path(final, repo_root))
