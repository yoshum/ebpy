"""Install ebpy in a project and manage its bundled Claude Code skills."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import tomllib
from dataclasses import dataclass
from importlib import metadata, resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, cast

from .. import __version__
from ..detect.package_manager import detect_package_manager
from ..models import PackageManager
from ..package_manager import DEV_INSTALL_PREFIXES, RUN_PREFIXES
from ..util import run

REPOSITORY_URL = "https://github.com/yoshum/ebpy"
MANIFEST_NAME = ".ebpy-manifest.json"
MINIMUM_INSTALL_VERSION = "0.3.0"
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[.-][0-9A-Za-z]+)*")
REF_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._/-]*")


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class Bundle:
    files: dict[Path, bytes]
    managed_roots: tuple[str, ...]
    skill_count: int


@dataclass(frozen=True)
class InstallTarget:
    revision: str
    description: str


class _BundleInstallError(Exception):
    def __init__(self, message: str, *, preserve_temporary: bool = False) -> None:
        super().__init__(message)
        self.preserve_temporary = preserve_temporary


def _direct_url_data() -> dict[str, object] | None:
    try:
        direct_url = metadata.distribution("ebpy").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return None
    if not direct_url:
        return None
    try:
        loaded: object = json.loads(direct_url)
    except json.JSONDecodeError:
        return None
    return cast(dict[str, object], loaded) if isinstance(loaded, dict) else None


def _current_source() -> str:
    data = _direct_url_data()
    if data is not None:
        url = data.get("url")
        vcs = data.get("vcs_info")
        if isinstance(url, str) and isinstance(vcs, dict):
            commit = cast(dict[str, object], vcs).get("commit_id")
            if isinstance(commit, str) and commit:
                git_url = url if url.startswith("git+") else f"git+{url}"
                return f"{git_url}@{commit}"
        if isinstance(url, str):
            return url
    return f"v{__version__}"


def _bootstrap_ref() -> str | None:
    data = _direct_url_data()
    vcs = data.get("vcs_info") if data is not None else None
    if not isinstance(vcs, dict):
        return None
    requested = cast(dict[str, object], vcs).get("requested_revision")
    return requested if isinstance(requested, str) and requested else None


def _project_manager(cwd: Path) -> PackageManager:
    root_entries = tuple(sorted(entry.name for entry in cwd.iterdir() if entry.is_file()))
    try:
        pyproject: dict[str, Any] | None = tomllib.loads((cwd / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        pyproject = None
    return detect_package_manager(root_entries, pyproject)


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


def _load_bundle() -> Bundle:
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


def _swap_staged_bundle(destination: Path, stage: Path, backup: Path, bundle: Bundle) -> None:
    manifest_hashes = _manifest_hashes(destination)
    managed_entries = (
        *(Path(root) for root in _managed_roots(bundle, manifest_hashes)),
        Path(MANIFEST_NAME),
    )
    backup.mkdir()
    moved_old: list[Path] = []
    installed: list[Path] = []
    try:
        for relative in managed_entries:
            target = destination / relative
            if _path_exists(target):
                _replace_path(target, backup / relative)
                moved_old.append(relative)
        for relative in _bundle_entries(bundle):
            _replace_path(stage / relative, destination / relative)
            installed.append(relative)
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


def _write_bundle(cwd: Path, destination: Path, bundle: Bundle) -> None:
    temporary_root: Path | None = None
    preserve_temporary = False
    try:
        temporary_root = Path(tempfile.mkdtemp(prefix=".ebpy-skills-", dir=cwd))
        stage = temporary_root / "stage"
        _stage_bundle(stage, bundle)
        destination.mkdir(parents=True, exist_ok=True)
        _swap_staged_bundle(destination, stage, temporary_root / "backup", bundle)
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


def run_skills_install(cwd: Path, force: bool) -> InstallResult:
    if not (cwd / "pyproject.toml").is_file():
        return InstallResult(False, f"No pyproject.toml in {cwd}; run this from the project root.")

    try:
        bundle = _load_bundle()
    except FileNotFoundError as error:
        return InstallResult(False, str(error))

    destination = cwd / ".claude" / "skills"
    conflicts = _conflicts(destination, bundle, _manifest_hashes(destination))
    if conflicts and not force:
        names = ", ".join(conflicts)
        return InstallResult(
            False,
            "Refusing to overwrite locally changed ebpy skills: "
            f"{names}. Review them, then rerun with --force to replace them.",
        )

    try:
        _write_bundle(cwd, destination, bundle)
    except _BundleInstallError as error:
        return InstallResult(False, str(error))
    replaced = " Replaced the previous managed copies." if conflicts else ""
    return InstallResult(
        True,
        f"Installed {bundle.skill_count} Claude Code skills from ebpy v{__version__} "
        f"in .claude/skills.{replaced}",
    )


def _failure_detail(stdout: str, stderr: str) -> str:
    detail = stderr.strip() or stdout.strip()
    return f"\n{detail[:2000]}" if detail else ""


def _normalize_version(version: str) -> str | None:
    normalized = version.removeprefix("v")
    return normalized if VERSION_PATTERN.fullmatch(normalized) else None


def _valid_ref(ref: str) -> bool:
    return bool(
        REF_PATTERN.fullmatch(ref)
        and ".." not in ref
        and "@{" not in ref
        and not ref.endswith(("/", ".", ".lock"))
    )


def _release_target(version: str) -> InstallTarget | str:
    normalized = _normalize_version(version)
    if normalized is None:
        if _valid_ref(version):
            return f"{version!r} looks like a Git ref; use `--ref {version}` instead of VERSION."
        return (
            f"VERSION must be an exact release such as {MINIMUM_INSTALL_VERSION}; "
            "version ranges are not supported."
        )
    core_match = re.match(r"([0-9]+)\.([0-9]+)\.([0-9]+)", normalized)
    if core_match is None:  # Kept separate from the syntax regex so the comparison stays explicit.
        return f"Invalid release version: {version}"
    core = tuple(int(part) for part in core_match.groups())
    minimum = tuple(int(part) for part in MINIMUM_INSTALL_VERSION.split("."))
    if core < minimum:
        return (
            f"ebpy install supports v{MINIMUM_INSTALL_VERSION} or newer; "
            f"v{normalized} does not provide `ebpy skills install`."
        )
    revision = f"v{normalized}"
    return InstallTarget(revision, f"release {revision}")


def _ref_target(ref: str, *, bootstrap: bool = False) -> InstallTarget | str:
    if not _valid_ref(ref):
        return f"Invalid Git ref: {ref}"
    normalized = _normalize_version(ref)
    if normalized is not None:
        release = _release_target(normalized)
        if isinstance(release, str):
            return release
    qualifier = "bootstrap Git ref" if bootstrap else "Git ref"
    return InstallTarget(ref, f"{qualifier} {ref}")


def _resolve_target(version: str | None, ref: str | None, bootstrap_ref: str | None) -> InstallTarget | str:
    if version is not None and ref is not None:
        return "VERSION and --ref cannot be used together."
    if ref is not None:
        return _ref_target(ref)
    if version is not None:
        return _release_target(version)
    if bootstrap_ref is not None:
        return _ref_target(bootstrap_ref, bootstrap=True)
    return _release_target(__version__)


def _requirement(manager: PackageManager, target: InstallTarget) -> str:
    repository = f"{REPOSITORY_URL}.git" if manager == "pipenv" else REPOSITORY_URL
    vcs_url = f"git+{repository}@{target.revision}"
    return f"{vcs_url}#egg=ebpy" if manager == "pipenv" else f"ebpy @ {vcs_url}"


def run_install(cwd: Path, version: str | None, ref: str | None, force: bool) -> InstallResult:
    if not (cwd / "pyproject.toml").is_file():
        return InstallResult(False, f"No pyproject.toml in {cwd}; run this from the project root.")
    target = _resolve_target(version, ref, _bootstrap_ref())
    if isinstance(target, str):
        return InstallResult(False, target)

    manager = _project_manager(cwd)
    if manager == "pip":
        return InstallResult(
            False,
            "Could not detect a supported project package manager. `ebpy install` requires "
            "uv, Poetry, PDM, or Pipenv so it can persist ebpy as a development dependency.",
        )
    requirement = _requirement(manager, target)
    install_argv = [*DEV_INSTALL_PREFIXES[manager]]
    if manager == "pipenv":
        install_argv.append("--editable")
    install_argv.append(requirement)
    added = run(install_argv, cwd)
    if added.code != 0:
        return InstallResult(
            False,
            f"{manager} dependency installation failed for {target.description} (exit {added.code})."
            f"{_failure_detail(added.stdout, added.stderr)}",
        )

    skills_argv = [*RUN_PREFIXES[manager], "ebpy", "skills", "install"]
    if force:
        skills_argv.append("--force")
    skills = run(skills_argv, cwd)
    if skills.code != 0:
        command = " ".join(skills_argv)
        return InstallResult(
            False,
            f"Added ebpy from {target.description}, but `{command}` failed "
            f"(exit {skills.code}). The dependency remains installed; after resolving the error, "
            f"retry `{command}`.{_failure_detail(skills.stdout, skills.stderr)}",
        )

    skill_message = skills.stdout.strip()
    suffix = f"\n{skill_message}" if skill_message else ""
    return InstallResult(
        True, f"Installed ebpy from {target.description} as a {manager} dev dependency.{suffix}"
    )
