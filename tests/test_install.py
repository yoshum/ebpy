from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from importlib import metadata as importlib_metadata
from pathlib import Path

import pytest

from ebpy import __version__
from ebpy.cli import main
from ebpy.commands import install
from ebpy.commands.install import REPOSITORY_URL, run_install, run_skills_install
from ebpy.models import PackageManager
from ebpy.util import ExecResult


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").touch()
    return tmp_path


@pytest.fixture
def skill_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "bundle"
    (root / "_shared").mkdir(parents=True)
    (root / "_shared" / "ebpy-command.md").write_text("shared\n", encoding="utf-8")
    for name in ("ebpy-guide", "ebpy-run"):
        skill = root / name
        skill.mkdir()
        (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    monkeypatch.setattr(install, "_skills_root", lambda: root)
    monkeypatch.setattr(install, "_current_source", lambda: "git+https://example.test/ebpy@abc123")
    return root


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


def test_skills_install_copies_all_bundled_skills(
    project: Path,
    skill_bundle: Path,
) -> None:
    result = run_skills_install(project, force=False)

    assert result.ok
    destination = project / ".claude" / "skills"
    assert (destination / "ebpy-guide" / "SKILL.md").read_bytes() == (
        skill_bundle / "ebpy-guide" / "SKILL.md"
    ).read_bytes()
    assert (destination / "_shared" / "ebpy-command.md").is_file()
    manifest = json.loads((destination / ".ebpy-manifest.json").read_text(encoding="utf-8"))
    assert manifest["ebpyVersion"] == __version__
    assert manifest["source"] == "git+https://example.test/ebpy@abc123"
    assert set(manifest["files"]) == {
        "_shared/ebpy-command.md",
        "ebpy-guide/SKILL.md",
        "ebpy-run/SKILL.md",
    }


@pytest.mark.usefixtures("skill_bundle")
def test_skills_install_is_idempotent(project: Path) -> None:
    assert run_skills_install(project, force=False).ok
    assert run_skills_install(project, force=False).ok


def test_unedited_skills_are_updated_from_the_previous_manifest(
    project: Path,
    skill_bundle: Path,
) -> None:
    assert run_skills_install(project, force=False).ok
    updated = skill_bundle / "ebpy-guide" / "SKILL.md"
    updated.write_text("---\nname: ebpy-guide\n---\nupdated\n", encoding="utf-8")

    result = run_skills_install(project, force=False)

    assert result.ok
    installed = project / ".claude" / "skills" / "ebpy-guide" / "SKILL.md"
    assert installed.read_bytes() == updated.read_bytes()


def test_a_removed_bundled_skill_is_removed_from_the_project(
    project: Path,
    skill_bundle: Path,
) -> None:
    assert run_skills_install(project, force=False).ok
    removed = project / ".claude" / "skills" / "ebpy-guide"
    unrelated = project / ".claude" / "skills" / "team-skill" / "SKILL.md"
    unrelated.parent.mkdir()
    unrelated.write_text("keep me\n", encoding="utf-8")
    shutil.rmtree(skill_bundle / "ebpy-guide")

    result = run_skills_install(project, force=False)

    assert result.ok
    assert not removed.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep me\n"
    manifest = json.loads(
        (project / ".claude" / "skills" / ".ebpy-manifest.json").read_text(encoding="utf-8")
    )
    assert "ebpy-guide/SKILL.md" not in manifest["files"]


def test_a_locally_edited_removed_skill_requires_force(
    project: Path,
    skill_bundle: Path,
) -> None:
    assert run_skills_install(project, force=False).ok
    removed = project / ".claude" / "skills" / "ebpy-guide"
    (removed / "SKILL.md").write_text("locally edited\n", encoding="utf-8")
    shutil.rmtree(skill_bundle / "ebpy-guide")

    refused = run_skills_install(project, force=False)
    replaced = run_skills_install(project, force=True)

    assert not refused.ok
    assert "ebpy-guide" in refused.message
    assert "--force" in refused.message
    assert replaced.ok
    assert not removed.exists()


def test_a_staging_failure_leaves_the_installed_bundle_unchanged(
    project: Path,
    skill_bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run_skills_install(project, force=False).ok
    destination = project / ".claude" / "skills"
    before = {
        path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()
    }
    (skill_bundle / "ebpy-guide" / "SKILL.md").write_text("updated\n", encoding="utf-8")

    def fail_staging(_destination: Path, _bundle: install.Bundle) -> None:
        raise OSError("disk full while staging")

    monkeypatch.setattr(install, "_stage_bundle", fail_staging)
    result = run_skills_install(project, force=False)

    after = {
        path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()
    }
    assert not result.ok
    assert "were not changed" in result.message
    assert after == before


def test_a_partial_swap_restores_the_previous_bundle(
    project: Path,
    skill_bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run_skills_install(project, force=False).ok
    destination = project / ".claude" / "skills"
    unrelated = destination / "team-skill" / "SKILL.md"
    unrelated.parent.mkdir()
    unrelated.write_text("keep me\n", encoding="utf-8")
    before = {
        path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()
    }
    (skill_bundle / "ebpy-guide" / "SKILL.md").write_text("updated\n", encoding="utf-8")

    original_replace = install._replace_path
    failed = False

    def fail_during_swap(source: Path, target: Path) -> None:
        nonlocal failed
        if not failed and source.parent.name == "stage" and source.name == "ebpy-run":
            failed = True
            raise OSError("disk full during swap")
        original_replace(source, target)

    monkeypatch.setattr(install, "_replace_path", fail_during_swap)
    result = run_skills_install(project, force=False)

    after = {
        path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()
    }
    assert not result.ok
    assert "previous managed skills were restored" in result.message
    assert after == before
    assert not list(project.glob(".ebpy-skills-*"))


def test_an_incomplete_rollback_preserves_recovery_files(
    project: Path,
    skill_bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run_skills_install(project, force=False).ok
    (skill_bundle / "ebpy-guide" / "SKILL.md").write_text("updated\n", encoding="utf-8")
    original_replace = install._replace_path
    swap_failed = False

    def fail_swap_and_restore(source: Path, target: Path) -> None:
        nonlocal swap_failed
        if not swap_failed and source.parent.name == "stage" and source.name == "ebpy-run":
            swap_failed = True
            raise OSError("swap failed")
        if swap_failed and source.parent.name == "backup" and source.name == "ebpy-guide":
            raise OSError("restore failed")
        original_replace(source, target)

    monkeypatch.setattr(install, "_replace_path", fail_swap_and_restore)
    result = run_skills_install(project, force=False)

    recovery = list(project.glob(".ebpy-skills-*"))
    assert not result.ok
    assert "rollback was incomplete" in result.message
    assert "Recovery files remain" in result.message
    assert len(recovery) == 1
    assert (recovery[0] / "backup" / "ebpy-guide" / "SKILL.md").is_file()


@pytest.mark.usefixtures("skill_bundle")
def test_a_local_skill_edit_requires_force(project: Path) -> None:
    assert run_skills_install(project, force=False).ok
    (project / ".claude" / "skills" / "ebpy-guide" / "SKILL.md").write_text(
        "locally edited\n", encoding="utf-8"
    )

    result = run_skills_install(project, force=False)

    assert not result.ok
    assert "ebpy-guide" in result.message
    assert "--force" in result.message


def test_an_empty_managed_directory_is_not_a_local_edit(
    project: Path,
    skill_bundle: Path,
) -> None:
    empty = project / ".claude" / "skills" / "ebpy-guide"
    empty.mkdir(parents=True)

    result = run_skills_install(project, force=False)

    assert result.ok
    assert (empty / "SKILL.md").read_bytes() == (skill_bundle / "ebpy-guide" / "SKILL.md").read_bytes()


def test_force_replaces_only_ebpys_managed_directories(
    project: Path,
    skill_bundle: Path,
) -> None:
    destination = project / ".claude" / "skills"
    ours = destination / "ebpy-guide"
    ours.mkdir(parents=True)
    (ours / "SKILL.md").write_text("locally edited\n", encoding="utf-8")
    unrelated = destination / "team-skill" / "SKILL.md"
    unrelated.parent.mkdir()
    unrelated.write_text("keep me\n", encoding="utf-8")

    result = run_skills_install(project, force=True)

    assert result.ok
    assert "Replaced" in result.message
    assert (ours / "SKILL.md").read_bytes() == (skill_bundle / "ebpy-guide" / "SKILL.md").read_bytes()
    assert unrelated.read_text(encoding="utf-8") == "keep me\n"


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
    [("0.1.0", None), ("v0.2.0", None), (None, "v0.2.0")],
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
        ("pip", ["pip", "install"], []),
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


def test_install_commands_require_the_project_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--cwd", str(tmp_path), "install", "1.2.3"]) == 1
    assert "pyproject.toml" in capsys.readouterr().out

    assert main(["skills", "install", "--cwd", str(tmp_path)]) == 1
    assert "pyproject.toml" in capsys.readouterr().out


def test_the_built_wheel_contains_all_bundled_skills(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1

    with zipfile.ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
    skill_files = {name for name in names if name.startswith("ebpy/_skills/") and name.endswith("/SKILL.md")}
    assert len(skill_files) == 5
    assert "ebpy/_skills/_shared/ebpy-command.md" in names
