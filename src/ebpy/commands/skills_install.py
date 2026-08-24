"""Swap ebpy's bundled Claude Code skills onto disk transactionally."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import cast

from .. import __version__
from .install import InstallResult, _current_source

MANIFEST_NAME = ".ebpy-manifest.json"


@dataclass(frozen=True)
class Bundle:
    files: dict[Path, bytes]
    managed_roots: tuple[str, ...]
    skill_count: int


class _BundleInstallError(Exception):
    def __init__(self, message: str, *, preserve_temporary: bool = False) -> None:
        super().__init__(message)
        self.preserve_temporary = preserve_temporary


def _skills_root() -> Traversable:
    packaged = resources.files("ebpy").joinpath("_skills")
    if packaged.is_dir():
        return packaged

    # Tests and editable source checkouts import straight from src/, before Hatch has
    # force-included the resources into a wheel.
    source_checkout = Path(__file__).resolve().parents[3] / "skills"
    if source_checkout.is_dir():
        return source_checkout
    raise FileNotFoundError("ebpy's bundled skills are missing")


def _read_files(root: Traversable, relative: Path = Path()) -> dict[Path, bytes]:
    found: dict[Path, bytes] = {}
    for child in sorted(root.iterdir(), key=lambda entry: entry.name):
        child_relative = relative / child.name
        if child.is_dir():
            found.update(_read_files(child, child_relative))
        elif child.is_file():
            found[child_relative] = child.read_bytes()
    return found


def load_bundle() -> Bundle:
    files = _read_files(_skills_root())
    if not files:
        raise FileNotFoundError("ebpy's bundled skills are empty")
    roots = tuple(sorted({path.parts[0] for path in files}))
    skill_count = sum(path.name == "SKILL.md" for path in files)
    return Bundle(files=files, managed_roots=roots, skill_count=skill_count)


def _files_below(root: Path) -> dict[Path, bytes] | None:
    if not root.exists():
        return {}
    if root.is_symlink() or not root.is_dir():
        return None
    return {path.relative_to(root): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _manifest_hashes(destination: Path) -> dict[Path, str]:
    manifest_path = destination / MANIFEST_NAME
    try:
        loaded: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    files = cast(dict[str, object], loaded).get("files")
    if not isinstance(files, dict):
        return {}
    return {
        Path(relative): digest
        for relative, digest in cast(dict[str, object], files).items()
        if isinstance(relative, str) and isinstance(digest, str)
    }


def _matches_manifest(actual: dict[Path, bytes] | None, hashes: dict[Path, str]) -> bool:
    return (
        bool(hashes)
        and actual is not None
        and set(actual) == set(hashes)
        and all(
            hashlib.sha256(content).hexdigest() == hashes[relative] for relative, content in actual.items()
        )
    )


def _manifest_roots(hashes: dict[Path, str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                relative.parts[0]
                for relative in hashes
                if not relative.is_absolute()
                and len(relative.parts) > 1
                and relative.parts[0] not in {".", "..", MANIFEST_NAME}
            }
        )
    )


def _managed_roots(bundle: Bundle, manifest_hashes: dict[Path, str]) -> tuple[str, ...]:
    return tuple(sorted(set(bundle.managed_roots) | set(_manifest_roots(manifest_hashes))))


def _conflicts(destination: Path, bundle: Bundle, manifest_hashes: dict[Path, str]) -> list[str]:
    conflicts: list[str] = []
    for root_name in _managed_roots(bundle, manifest_hashes):
        target = destination / root_name
        actual = _files_below(target)
        if actual == {}:
            continue
        expected = {
            Path(*relative.parts[1:]): content
            for relative, content in bundle.files.items()
            if relative.parts[0] == root_name
        }
        recorded = {
            Path(*relative.parts[1:]): digest
            for relative, digest in manifest_hashes.items()
            if relative.parts and relative.parts[0] == root_name
        }
        if actual != expected and not _matches_manifest(actual, recorded):
            conflicts.append(root_name)
    return conflicts


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _remove_path(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _replace_path(source: Path, target: Path) -> None:
    source.replace(target)


def _stage_bundle(destination: Path, bundle: Bundle) -> None:
    destination.mkdir(parents=True)
    for relative, content in bundle.files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    hashes = {
        relative.as_posix(): hashlib.sha256(content).hexdigest()
        for relative, content in sorted(bundle.files.items())
    }
    manifest = {
        "schemaVersion": 1,
        "ebpyVersion": __version__,
        "source": _current_source(),
        "files": hashes,
    }
    (destination / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _bundle_entries(bundle: Bundle) -> tuple[Path, ...]:
    return (*(Path(root) for root in bundle.managed_roots), Path(MANIFEST_NAME))


def _rollback_bundle(
    destination: Path,
    backup: Path,
    installed: list[Path],
    moved_old: list[Path],
) -> list[str]:
    errors: list[str] = []
    for relative in reversed(installed):
        try:
            _remove_path(destination / relative)
        except OSError as error:
            errors.append(f"remove {relative}: {error}")
    for relative in reversed(moved_old):
        target = destination / relative
        try:
            if _path_exists(target):
                _remove_path(target)
            _replace_path(backup / relative, target)
        except OSError as error:
            errors.append(f"restore {relative}: {error}")
    return errors


def _move_existing_aside(
    destination: Path, backup: Path, managed_entries: tuple[Path, ...], moved_old: list[Path]
) -> None:
    """Move each currently installed managed entry into ``backup``, recording progress.

    ``moved_old`` is appended in place so a caller catching a mid-loop failure still
    knows which entries were moved and can roll them back.
    """
    for relative in managed_entries:
        target = destination / relative
        if _path_exists(target):
            _replace_path(target, backup / relative)
            moved_old.append(relative)


def _move_staged_into_place(destination: Path, stage: Path, bundle: Bundle, installed: list[Path]) -> None:
    """Move each staged bundle entry onto ``destination``, recording progress.

    ``installed`` is appended in place so a mid-loop failure leaves the caller the
    list of entries to undo during rollback.
    """
    for relative in _bundle_entries(bundle):
        _replace_path(stage / relative, destination / relative)
        installed.append(relative)


def _swap_staged_bundle(
    destination: Path, stage: Path, backup: Path, bundle: Bundle, manifest_hashes: dict[Path, str]
) -> None:
    managed_entries = (
        *(Path(root) for root in _managed_roots(bundle, manifest_hashes)),
        Path(MANIFEST_NAME),
    )
    backup.mkdir()
    moved_old: list[Path] = []
    installed: list[Path] = []
    try:
        _move_existing_aside(destination, backup, managed_entries, moved_old)
        _move_staged_into_place(destination, stage, bundle, installed)
    except OSError as error:
        rollback_errors = _rollback_bundle(destination, backup, installed, moved_old)
        if rollback_errors:
            detail = "; ".join(rollback_errors)
            raise _BundleInstallError(
                f"Could not replace the managed ebpy skills ({error}); rollback was incomplete: {detail}. "
                f"Recovery files remain in {backup.parent}.",
                preserve_temporary=True,
            ) from error
        raise _BundleInstallError(
            f"Could not replace the managed ebpy skills ({error}); previous managed skills were restored."
        ) from error


def _write_bundle(cwd: Path, destination: Path, bundle: Bundle, manifest_hashes: dict[Path, str]) -> None:
    temporary_root: Path | None = None
    preserve_temporary = False
    try:
        temporary_root = Path(tempfile.mkdtemp(prefix=".ebpy-skills-", dir=cwd))
        stage = temporary_root / "stage"
        _stage_bundle(stage, bundle)
        destination.mkdir(parents=True, exist_ok=True)
        _swap_staged_bundle(destination, stage, temporary_root / "backup", bundle, manifest_hashes)
    except _BundleInstallError as error:
        preserve_temporary = error.preserve_temporary
        raise
    except OSError as error:
        raise _BundleInstallError(
            f"Could not stage the ebpy skills ({error}); existing managed skills were not changed."
        ) from error
    finally:
        if temporary_root is not None and not preserve_temporary:
            shutil.rmtree(temporary_root, ignore_errors=True)


def run_skills_install(cwd: Path, force: bool, bundle: Bundle | None = None) -> InstallResult:
    if not (cwd / "pyproject.toml").is_file():
        return InstallResult(False, f"No pyproject.toml in {cwd}; run this from the project root.")

    if bundle is None:
        try:
            bundle = load_bundle()
        except FileNotFoundError as error:
            return InstallResult(False, str(error))

    destination = cwd / ".claude" / "skills"
    try:
        manifest_hashes = _manifest_hashes(destination)
        conflicts = _conflicts(destination, bundle, manifest_hashes)
    except OSError as error:
        return InstallResult(
            False,
            f"Could not inspect the existing managed ebpy skills ({error}); "
            "existing skills were not changed.",
        )
    if conflicts and not force:
        names = ", ".join(conflicts)
        return InstallResult(
            False,
            "Refusing to overwrite locally changed ebpy skills: "
            f"{names}. Review them, then rerun with --force to replace them.",
        )

    try:
        _write_bundle(cwd, destination, bundle, manifest_hashes)
    except _BundleInstallError as error:
        return InstallResult(False, str(error))
    replaced = " Replaced the previous managed copies." if conflicts else ""
    skill_noun = "skill" if bundle.skill_count == 1 else "skills"
    return InstallResult(
        True,
        f"Installed {bundle.skill_count} Claude Code {skill_noun} from ebpy v{__version__} "
        f"in .claude/skills.{replaced}",
    )
