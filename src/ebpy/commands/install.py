"""Pin ebpy as a project's development dependency."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, cast

from .. import __version__
from ..models import PackageManager
from ..package_manager import DEV_INSTALL_PREFIXES, RUN_PREFIXES
from ..repo.detect.package_manager import detect_package_manager
from ..util import run

REPOSITORY_URL = "https://github.com/yoshum/ebpy"
MINIMUM_INSTALL_VERSION = "0.3.0"
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[.-][0-9A-Za-z]+)*")
REF_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._/-]*")


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class InstallTarget:
    revision: str
    description: str


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
    normalized = _normalize_version(ref.removeprefix("refs/tags/"))
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
