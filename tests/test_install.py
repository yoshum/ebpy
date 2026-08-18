from __future__ import annotations

import json
from pathlib import Path

import pytest

from ebpy import __version__
from ebpy.cli import main
from ebpy.commands import install
from ebpy.commands.install import REPOSITORY_URL, run_install, run_skills_install
from ebpy.util import ExecResult


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\nversion = "0.1.0"\n', encoding="utf-8"
    )
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


def test_install_defaults_to_its_own_exact_release(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv)
        return ExecResult(0, "skills installed\n" if argv[1] == "run" else "", "")

    monkeypatch.setattr(install, "run", fake_run)
    result = run_install(project, version=None, ref=None, force=False)

    assert result.ok
    assert calls == [
        ["uv", "add", "--dev", f"ebpy @ git+{REPOSITORY_URL}@v{__version__}"],
        ["uv", "run", "ebpy", "skills", "install"],
    ]
    assert "skills installed" in result.message


@pytest.mark.parametrize("version", ["1.2.3", "v1.2.3"])
def test_install_accepts_an_exact_release(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    version: str,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv)
        return ExecResult(0, "", "")

    monkeypatch.setattr(install, "run", fake_run)
    assert run_install(project, version=version, ref=None, force=False).ok
    assert calls[0] == ["uv", "add", "--dev", f"ebpy @ git+{REPOSITORY_URL}@v1.2.3"]


@pytest.mark.parametrize("ref", ["feature/install", "abc123def456"])
def test_install_accepts_a_commit_or_branch(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    ref: str,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv)
        return ExecResult(0, "", "")

    monkeypatch.setattr(install, "run", fake_run)
    assert run_install(project, version=None, ref=ref, force=False).ok
    assert calls[0] == ["uv", "add", "--dev", f"ebpy @ git+{REPOSITORY_URL}@{ref}"]


@pytest.mark.parametrize("version", [">=1.2,<2", "1.*", "main"])
def test_install_rejects_non_exact_versions_before_uv(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    version: str,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv)
        return ExecResult(0, "", "")

    monkeypatch.setattr(install, "run", fake_run)

    result = run_install(project, version=version, ref=None, force=False)

    assert not result.ok
    assert "version ranges are not supported" in result.message
    assert calls == []


def test_install_rejects_version_and_ref_together(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv)
        return ExecResult(0, "", "")

    monkeypatch.setattr(install, "run", fake_run)

    result = run_install(project, version="1.2.3", ref="main", force=False)

    assert not result.ok
    assert "cannot be used together" in result.message
    assert calls == []


def test_install_passes_force_only_to_skills_install(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv)
        return ExecResult(0, "", "")

    monkeypatch.setattr(install, "run", fake_run)
    assert run_install(project, version=None, ref=None, force=True).ok
    assert "--force" not in calls[0]
    assert calls[1][-1] == "--force"


def test_uv_add_failure_does_not_install_skills(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv)
        return ExecResult(1, "", "resolution failed")

    monkeypatch.setattr(install, "run", fake_run)
    result = run_install(project, version=None, ref=None, force=False)

    assert not result.ok
    assert "resolution failed" in result.message
    assert len(calls) == 1


def test_skills_failure_reports_that_dependency_was_added(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter([ExecResult(0, "", ""), ExecResult(1, "", "skill conflict")])
    monkeypatch.setattr(install, "run", lambda _argv, _cwd: next(results))

    result = run_install(project, version=None, ref="feature/install", force=False)

    assert not result.ok
    assert "Added ebpy from Git ref feature/install" in result.message
    assert "skill conflict" in result.message


def test_install_commands_require_the_project_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--cwd", str(tmp_path), "install"]) == 1
    assert "pyproject.toml" in capsys.readouterr().out

    assert main(["skills", "install", "--cwd", str(tmp_path)]) == 1
    assert "pyproject.toml" in capsys.readouterr().out
