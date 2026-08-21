from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from ebpy import __version__
from ebpy.cli import main
from ebpy.commands import skills_install
from ebpy.commands.skills_install import Bundle, run_skills_install


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").touch()
    return tmp_path


@dataclass(frozen=True)
class SkillBundleSource:
    """A bundle laid out on disk that tests mutate between installs.

    ``load`` reads the current tree, so a test can edit or remove files and then
    hand ``run_skills_install`` the resulting bundle without patching the packaged
    resource lookup.
    """

    root: Path

    def load(self) -> Bundle:
        files = {
            path.relative_to(self.root): path.read_bytes()
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }
        roots = tuple(sorted({relative.parts[0] for relative in files}))
        skill_count = sum(relative.name == "SKILL.md" for relative in files)
        return Bundle(files=files, managed_roots=roots, skill_count=skill_count)


@pytest.fixture
def skill_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SkillBundleSource:
    root = tmp_path / "bundle"
    (root / "_shared").mkdir(parents=True)
    (root / "_shared" / "ebpy-command.md").write_text("shared\n", encoding="utf-8")
    for name in ("ebpy-guide", "ebpy-run"):
        skill = root / name
        skill.mkdir()
        (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    # _current_source stamps the manifest from ebpy's own install metadata, so it stays
    # patched even though the bundle itself is now injected.
    monkeypatch.setattr(skills_install, "_current_source", lambda: "git+https://example.test/ebpy@abc123")
    return SkillBundleSource(root)


def test_skills_install_copies_all_bundled_skills(
    project: Path,
    skill_bundle: SkillBundleSource,
) -> None:
    result = run_skills_install(project, force=False, bundle=skill_bundle.load())

    assert result.ok
    destination = project / ".claude" / "skills"
    assert (destination / "ebpy-guide" / "SKILL.md").read_bytes() == (
        skill_bundle.root / "ebpy-guide" / "SKILL.md"
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


def test_skills_install_uses_the_singular_noun_for_one_skill(
    project: Path,
    skill_bundle: SkillBundleSource,
) -> None:
    shutil.rmtree(skill_bundle.root / "ebpy-guide")

    result = run_skills_install(project, force=False, bundle=skill_bundle.load())

    assert result.ok
    assert "Installed 1 Claude Code skill from" in result.message


def test_skills_install_is_idempotent(project: Path, skill_bundle: SkillBundleSource) -> None:
    assert run_skills_install(project, force=False, bundle=skill_bundle.load()).ok
    assert run_skills_install(project, force=False, bundle=skill_bundle.load()).ok


def test_skills_install_defaults_to_the_packaged_bundle(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Bundle] = []
    marker = Bundle(files={Path("ebpy-run/SKILL.md"): b"x"}, managed_roots=("ebpy-run",), skill_count=1)

    def fake_load_bundle() -> Bundle:
        captured.append(marker)
        return marker

    monkeypatch.setattr(skills_install, "load_bundle", fake_load_bundle)
    monkeypatch.setattr(skills_install, "_current_source", lambda: "v0.0.0")

    result = run_skills_install(project, force=False)

    assert result.ok
    assert captured == [marker]


def test_unedited_skills_are_updated_from_the_previous_manifest(
    project: Path,
    skill_bundle: SkillBundleSource,
) -> None:
    assert run_skills_install(project, force=False, bundle=skill_bundle.load()).ok
    updated = skill_bundle.root / "ebpy-guide" / "SKILL.md"
    updated.write_text("---\nname: ebpy-guide\n---\nupdated\n", encoding="utf-8")

    result = run_skills_install(project, force=False, bundle=skill_bundle.load())

    assert result.ok
    installed = project / ".claude" / "skills" / "ebpy-guide" / "SKILL.md"
    assert installed.read_bytes() == updated.read_bytes()


def test_a_removed_bundled_skill_is_removed_from_the_project(
    project: Path,
    skill_bundle: SkillBundleSource,
) -> None:
    assert run_skills_install(project, force=False, bundle=skill_bundle.load()).ok
    removed = project / ".claude" / "skills" / "ebpy-guide"
    unrelated = project / ".claude" / "skills" / "team-skill" / "SKILL.md"
    unrelated.parent.mkdir()
    unrelated.write_text("keep me\n", encoding="utf-8")
    shutil.rmtree(skill_bundle.root / "ebpy-guide")

    result = run_skills_install(project, force=False, bundle=skill_bundle.load())

    assert result.ok
    assert not removed.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep me\n"
    manifest = json.loads(
        (project / ".claude" / "skills" / ".ebpy-manifest.json").read_text(encoding="utf-8")
    )
    assert "ebpy-guide/SKILL.md" not in manifest["files"]


def test_a_locally_edited_removed_skill_requires_force(
    project: Path,
    skill_bundle: SkillBundleSource,
) -> None:
    assert run_skills_install(project, force=False, bundle=skill_bundle.load()).ok
    removed = project / ".claude" / "skills" / "ebpy-guide"
    (removed / "SKILL.md").write_text("locally edited\n", encoding="utf-8")
    shutil.rmtree(skill_bundle.root / "ebpy-guide")

    refused = run_skills_install(project, force=False, bundle=skill_bundle.load())
    replaced = run_skills_install(project, force=True, bundle=skill_bundle.load())

    assert not refused.ok
    assert "ebpy-guide" in refused.message
    assert "--force" in refused.message
    assert replaced.ok
    assert not removed.exists()


def test_an_unreadable_managed_file_reports_an_error_without_changing_skills(
    project: Path,
    skill_bundle: SkillBundleSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run_skills_install(project, force=False, bundle=skill_bundle.load()).ok
    destination = project / ".claude" / "skills"
    before = {
        path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()
    }

    def fail_inspection(_root: Path) -> dict[Path, bytes] | None:
        raise PermissionError("permission denied")

    monkeypatch.setattr(skills_install, "_files_below", fail_inspection)
    result = run_skills_install(project, force=False, bundle=skill_bundle.load())
    after = {
        path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()
    }

    assert not result.ok
    assert "Could not inspect the existing managed ebpy skills" in result.message
    assert "permission denied" in result.message
    assert "were not changed" in result.message
    assert after == before


def test_a_staging_failure_leaves_the_installed_bundle_unchanged(
    project: Path,
    skill_bundle: SkillBundleSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run_skills_install(project, force=False, bundle=skill_bundle.load()).ok
    destination = project / ".claude" / "skills"
    before = {
        path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()
    }
    (skill_bundle.root / "ebpy-guide" / "SKILL.md").write_text("updated\n", encoding="utf-8")

    def fail_staging(_destination: Path, _bundle: Bundle) -> None:
        raise OSError("disk full while staging")

    monkeypatch.setattr(skills_install, "_stage_bundle", fail_staging)
    result = run_skills_install(project, force=False, bundle=skill_bundle.load())

    after = {
        path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()
    }
    assert not result.ok
    assert "were not changed" in result.message
    assert after == before


def test_a_partial_swap_restores_the_previous_bundle(
    project: Path,
    skill_bundle: SkillBundleSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run_skills_install(project, force=False, bundle=skill_bundle.load()).ok
    destination = project / ".claude" / "skills"
    unrelated = destination / "team-skill" / "SKILL.md"
    unrelated.parent.mkdir()
    unrelated.write_text("keep me\n", encoding="utf-8")
    before = {
        path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()
    }
    (skill_bundle.root / "ebpy-guide" / "SKILL.md").write_text("updated\n", encoding="utf-8")

    original_replace = skills_install._replace_path
    failed = False

    def fail_during_swap(source: Path, target: Path) -> None:
        nonlocal failed
        if not failed and source.parent.name == "stage" and source.name == "ebpy-run":
            failed = True
            raise OSError("disk full during swap")
        original_replace(source, target)

    monkeypatch.setattr(skills_install, "_replace_path", fail_during_swap)
    result = run_skills_install(project, force=False, bundle=skill_bundle.load())

    after = {
        path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()
    }
    assert not result.ok
    assert "previous managed skills were restored" in result.message
    assert after == before
    assert not list(project.glob(".ebpy-skills-*"))


def test_an_incomplete_rollback_preserves_recovery_files(
    project: Path,
    skill_bundle: SkillBundleSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run_skills_install(project, force=False, bundle=skill_bundle.load()).ok
    (skill_bundle.root / "ebpy-guide" / "SKILL.md").write_text("updated\n", encoding="utf-8")
    original_replace = skills_install._replace_path
    swap_failed = False

    def fail_swap_and_restore(source: Path, target: Path) -> None:
        nonlocal swap_failed
        if not swap_failed and source.parent.name == "stage" and source.name == "ebpy-run":
            swap_failed = True
            raise OSError("swap failed")
        if swap_failed and source.parent.name == "backup" and source.name == "ebpy-guide":
            raise OSError("restore failed")
        original_replace(source, target)

    monkeypatch.setattr(skills_install, "_replace_path", fail_swap_and_restore)
    result = run_skills_install(project, force=False, bundle=skill_bundle.load())

    recovery = list(project.glob(".ebpy-skills-*"))
    assert not result.ok
    assert "rollback was incomplete" in result.message
    assert "Recovery files remain" in result.message
    assert len(recovery) == 1
    assert (recovery[0] / "backup" / "ebpy-guide" / "SKILL.md").is_file()


def test_a_local_skill_edit_requires_force(project: Path, skill_bundle: SkillBundleSource) -> None:
    assert run_skills_install(project, force=False, bundle=skill_bundle.load()).ok
    (project / ".claude" / "skills" / "ebpy-guide" / "SKILL.md").write_text(
        "locally edited\n", encoding="utf-8"
    )

    result = run_skills_install(project, force=False, bundle=skill_bundle.load())

    assert not result.ok
    assert "ebpy-guide" in result.message
    assert "--force" in result.message


def test_an_empty_managed_directory_is_not_a_local_edit(
    project: Path,
    skill_bundle: SkillBundleSource,
) -> None:
    empty = project / ".claude" / "skills" / "ebpy-guide"
    empty.mkdir(parents=True)

    result = run_skills_install(project, force=False, bundle=skill_bundle.load())

    assert result.ok
    assert (empty / "SKILL.md").read_bytes() == (skill_bundle.root / "ebpy-guide" / "SKILL.md").read_bytes()


def test_force_replaces_only_ebpys_managed_directories(
    project: Path,
    skill_bundle: SkillBundleSource,
) -> None:
    destination = project / ".claude" / "skills"
    ours = destination / "ebpy-guide"
    ours.mkdir(parents=True)
    (ours / "SKILL.md").write_text("locally edited\n", encoding="utf-8")
    unrelated = destination / "team-skill" / "SKILL.md"
    unrelated.parent.mkdir()
    unrelated.write_text("keep me\n", encoding="utf-8")

    result = run_skills_install(project, force=True, bundle=skill_bundle.load())

    assert result.ok
    assert "Replaced" in result.message
    assert (ours / "SKILL.md").read_bytes() == (skill_bundle.root / "ebpy-guide" / "SKILL.md").read_bytes()
    assert unrelated.read_text(encoding="utf-8") == "keep me\n"


def test_skills_install_requires_the_project_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
