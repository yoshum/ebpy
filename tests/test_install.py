"""`ebpy install`: resolving the ref to pin, following the package manager, rejecting unsafe requests."""

from __future__ import annotations

import json
from importlib import metadata as importlib_metadata
from typing import TYPE_CHECKING

import pytest

from ebpy.cli import main
from ebpy.commands import install
from ebpy.commands.install import REPOSITORY_URL, run_install
from ebpy.util import ExecResult

if TYPE_CHECKING:
    from pathlib import Path

    from ebpy.models import PackageManager


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").touch()
    return tmp_path


@pytest.fixture
def successful_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv)
        return ExecResult(0, "", "")

    monkeypatch.setattr(install, "run", fake_run)
    return calls


def _select_manager(project: Path, manager: PackageManager) -> None:
    (project / "uv.lock").unlink(missing_ok=True)
    marker = {
        "uv": "uv.lock",
        "poetry": "poetry.lock",
        "pdm": "pdm.lock",
        "pipenv": "Pipfile",
        "pip": None,
    }[manager]
    if marker is not None:
        (project / marker).touch()


def test_install_defaults_to_the_release_recorded_on_main(
    project: Path,
    successful_calls: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(install, "__version__", "0.3.4")
    monkeypatch.setattr(install, "_bootstrap_ref", lambda: None)

    result = run_install(project, version=None, ref=None, force=False)

    assert result.ok
    assert successful_calls == [
        ["uv", "add", "--dev", f"ebpy @ git+{REPOSITORY_URL}@v0.3.4"],
        ["uv", "run", "ebpy", "skills", "install"],
    ]


def test_the_bootstrap_git_ref_is_preserved_when_the_cli_has_no_target(
    project: Path,
    successful_calls: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(install, "_bootstrap_ref", lambda: "feature/install")

    result = run_install(project, version=None, ref=None, force=False)

    assert result.ok
    assert successful_calls[0][-1].endswith("@feature/install")
    assert "bootstrap Git ref feature/install" in result.message


def test_the_requested_bootstrap_ref_comes_from_direct_url_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct_url = json.dumps(
        {
            "url": REPOSITORY_URL,
            "vcs_info": {
                "vcs": "git",
                "requested_revision": "abc123",
                "commit_id": "a" * 40,
            },
        }
    )

    class Distribution:
        def read_text(self, filename: str) -> str:
            assert filename == "direct_url.json"
            return direct_url

    monkeypatch.setattr(importlib_metadata, "distribution", lambda _name: Distribution())
    assert install._bootstrap_ref() == "abc123"


@pytest.mark.parametrize("version", ["1.2.3", "v1.2.3"])
def test_an_explicit_release_overrides_the_bootstrap_ref(
    project: Path,
    successful_calls: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
    version: str,
) -> None:
    monkeypatch.setattr(install, "_bootstrap_ref", lambda: "feature/install")

    assert run_install(project, version=version, ref=None, force=False).ok
    assert successful_calls[0][-1] == f"ebpy @ git+{REPOSITORY_URL}@v1.2.3"


def test_an_explicit_ref_overrides_the_bootstrap_ref(
    project: Path,
    successful_calls: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(install, "_bootstrap_ref", lambda: "feature/bootstrap")

    assert run_install(project, version=None, ref="feature/cli", force=False).ok
    assert successful_calls[0][-1].endswith("@feature/cli")


@pytest.mark.parametrize(
    ("version", "ref"),
    [
        ("0.1.0", None),
        ("v0.2.0", None),
        (None, "v0.2.0"),
        (None, "refs/tags/v0.2.0"),
    ],
)
def test_releases_without_skills_install_are_rejected_before_dependency_changes(
    project: Path,
    successful_calls: list[list[str]],
    version: str | None,
    ref: str | None,
) -> None:
    result = run_install(project, version=version, ref=ref, force=False)

    assert not result.ok
    assert "v0.3.0 or newer" in result.message
    assert "does not provide `ebpy skills install`" in result.message
    assert successful_calls == []


@pytest.mark.parametrize("version", [">=1.2,<2", "1.*"])
def test_version_ranges_are_rejected_before_dependency_changes(
    project: Path,
    successful_calls: list[list[str]],
    version: str,
) -> None:
    result = run_install(project, version=version, ref=None, force=False)

    assert not result.ok
    assert "version ranges are not supported" in result.message
    assert successful_calls == []


def test_a_git_ref_in_the_version_position_explains_the_ref_option(
    project: Path,
    successful_calls: list[list[str]],
) -> None:
    result = run_install(project, version="main", ref=None, force=False)

    assert not result.ok
    assert "`--ref main`" in result.message
    assert successful_calls == []


def test_install_rejects_version_and_ref_together(
    project: Path,
    successful_calls: list[list[str]],
) -> None:
    result = run_install(project, version="1.2.3", ref="main", force=False)

    assert not result.ok
    assert "cannot be used together" in result.message
    assert successful_calls == []


@pytest.mark.parametrize(
    ("manager", "install_prefix", "run_prefix"),
    [
        ("uv", ["uv", "add", "--dev"], ["uv", "run"]),
        ("poetry", ["poetry", "add", "--group", "dev"], ["poetry", "run"]),
        ("pdm", ["pdm", "add", "-d"], ["pdm", "run"]),
        ("pipenv", ["pipenv", "install", "--dev", "--editable"], ["pipenv", "run"]),
    ],
)
def test_install_follows_the_detected_project_manager(
    project: Path,
    successful_calls: list[list[str]],
    manager: PackageManager,
    install_prefix: list[str],
    run_prefix: list[str],
) -> None:
    _select_manager(project, manager)

    result = run_install(project, version="1.2.3", ref=None, force=False)

    assert result.ok
    expected_requirement = (
        f"git+{REPOSITORY_URL}.git@v1.2.3#egg=ebpy"
        if manager == "pipenv"
        else f"ebpy @ git+{REPOSITORY_URL}@v1.2.3"
    )
    assert successful_calls == [
        [*install_prefix, expected_requirement],
        [*run_prefix, "ebpy", "skills", "install"],
    ]


def test_install_rejects_the_pip_fallback_before_dependency_changes(
    project: Path,
    successful_calls: list[list[str]],
) -> None:
    _select_manager(project, "pip")

    result = run_install(project, version="1.2.3", ref=None, force=False)

    assert not result.ok
    assert "requires uv, Poetry, PDM, or Pipenv" in result.message
    assert "development dependency" in result.message
    assert successful_calls == []


def test_install_passes_force_only_to_skills_install(
    project: Path,
    successful_calls: list[list[str]],
) -> None:
    assert run_install(project, version="1.2.3", ref=None, force=True).ok
    assert "--force" not in successful_calls[0]
    assert successful_calls[1][-1] == "--force"


def test_dependency_failure_does_not_install_skills(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv)
        return ExecResult(1, "", "resolution failed")

    monkeypatch.setattr(install, "run", fake_run)
    result = run_install(project, version="1.2.3", ref=None, force=False)

    assert not result.ok
    assert "resolution failed" in result.message
    assert len(calls) == 1


def test_skills_failure_reports_that_dependency_was_added(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _select_manager(project, "poetry")
    results = iter([ExecResult(0, "", ""), ExecResult(1, "", "skill conflict")])
    monkeypatch.setattr(install, "run", lambda _argv, _cwd: next(results))

    result = run_install(project, version=None, ref="feature/install", force=False)

    assert not result.ok
    assert "Added ebpy from Git ref feature/install" in result.message
    assert "The dependency remains installed" in result.message
    assert "retry `poetry run ebpy skills install`" in result.message
    assert "skill conflict" in result.message


def test_install_requires_the_project_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--cwd", str(tmp_path), "install", "1.2.3"]) == 1
    assert "pyproject.toml" in capsys.readouterr().out
