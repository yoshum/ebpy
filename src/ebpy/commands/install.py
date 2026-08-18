"""Install ebpy in a uv project and manage its bundled Claude Code skills."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from importlib import metadata, resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import cast

from .. import __version__
from ..util import run

REPOSITORY_URL = "https://github.com/yoshum/ebpy"
MANIFEST_NAME = ".ebpy-manifest.json"
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


def _current_source() -> str:
    try:
        direct_url = metadata.distribution("ebpy").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        direct_url = None
    if direct_url:
        try:
            loaded: object = json.loads(direct_url)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            data = cast(dict[str, object], loaded)
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


def _conflicts(destination: Path, bundle: Bundle) -> list[str]:
    conflicts: list[str] = []
    manifest_hashes = _manifest_hashes(destination)
    for root_name in bundle.managed_roots:
        target = destination / root_name
        actual = _files_below(target)
        if actual == {} and not target.exists():
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


def _remove_managed_roots(destination: Path, roots: tuple[str, ...]) -> None:
    for root_name in roots:
        target = destination / root_name
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def _write_bundle(destination: Path, bundle: Bundle) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    _remove_managed_roots(destination, bundle.managed_roots)
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


def run_skills_install(cwd: Path, force: bool) -> InstallResult:
    if not (cwd / "pyproject.toml").is_file():
        return InstallResult(False, f"No pyproject.toml in {cwd}; run this from the uv project root.")

    try:
        bundle = _load_bundle()
    except FileNotFoundError as error:
        return InstallResult(False, str(error))

    destination = cwd / ".claude" / "skills"
    conflicts = _conflicts(destination, bundle)
    if conflicts and not force:
        names = ", ".join(conflicts)
        return InstallResult(
            False,
            "Refusing to overwrite locally changed ebpy skills: "
            f"{names}. Review them, then rerun with --force to replace them.",
        )

    _write_bundle(destination, bundle)
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


def _resolve_target(version: str | None, ref: str | None) -> InstallTarget | str:
    if version is not None and ref is not None:
        return "VERSION and --ref cannot be used together."
    if ref is not None:
        if not _valid_ref(ref):
            return f"Invalid Git ref: {ref}"
        return InstallTarget(ref, f"Git ref {ref}")

    requested_version = version or __version__
    normalized = _normalize_version(requested_version)
    if normalized is None:
        return f"VERSION must be an exact release such as {__version__}; version ranges are not supported."
    revision = f"v{normalized}"
    return InstallTarget(revision, f"release {revision}")


def run_install(cwd: Path, version: str | None, ref: str | None, force: bool) -> InstallResult:
    if not (cwd / "pyproject.toml").is_file():
        return InstallResult(False, f"No pyproject.toml in {cwd}; run this from the uv project root.")
    target = _resolve_target(version, ref)
    if isinstance(target, str):
        return InstallResult(False, target)

    requirement = f"ebpy @ git+{REPOSITORY_URL}@{target.revision}"
    added = run(["uv", "add", "--dev", requirement], cwd)
    if added.code != 0:
        return InstallResult(
            False,
            f"uv add failed for {target.description} (exit {added.code})."
            f"{_failure_detail(added.stdout, added.stderr)}",
        )

    skills_argv = ["uv", "run", "ebpy", "skills", "install"]
    if force:
        skills_argv.append("--force")
    skills = run(skills_argv, cwd)
    if skills.code != 0:
        return InstallResult(
            False,
            f"Added ebpy from {target.description}, but `uv run ebpy skills install` failed "
            f"(exit {skills.code}).{_failure_detail(skills.stdout, skills.stderr)}",
        )

    skill_message = skills.stdout.strip()
    suffix = f"\n{skill_message}" if skill_message else ""
    return InstallResult(True, f"Installed ebpy from {target.description} as a dev dependency.{suffix}")
