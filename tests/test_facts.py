"""Tests for the manifest and config facts gather_facts reads for the clippy analyzer."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from ebpy.repo.facts import InvalidToml, gather_facts


def test_a_cargo_manifest_is_parsed_into_the_facts(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[lints.clippy]\nall = 'warn'\n", encoding="utf-8")
    facts = gather_facts(tmp_path)
    manifest = facts.cargo_manifests[PurePosixPath("Cargo.toml")]
    assert isinstance(manifest, dict)
    assert manifest["lints"]["clippy"] == {"all": "warn"}


def test_an_unparseable_manifest_is_recorded_rather_than_flattened_to_false(tmp_path: Path) -> None:
    """An I/O failure and a clippy config that is simply absent must not read as the same fact."""
    (tmp_path / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    manifest = gather_facts(tmp_path).cargo_manifests[PurePosixPath("Cargo.toml")]
    assert isinstance(manifest, InvalidToml)
    assert manifest.path == PurePosixPath("Cargo.toml")


def test_a_badly_encoded_manifest_does_not_stop_every_command(tmp_path: Path) -> None:
    """UnicodeDecodeError is neither OSError nor TOMLDecodeError; missing it breaks gather_facts."""
    (tmp_path / "Cargo.toml").write_bytes(b"[package]\nname = '\xff\xfe'\n")
    manifest = gather_facts(tmp_path).cargo_manifests[PurePosixPath("Cargo.toml")]
    assert isinstance(manifest, InvalidToml)


def test_an_invalid_manifest_detail_never_carries_a_host_path(tmp_path: Path) -> None:
    """The diagnosis is persisted, so an absolute path would be baked into a committed artifact."""
    (tmp_path / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    manifest = gather_facts(tmp_path).cargo_manifests[PurePosixPath("Cargo.toml")]
    assert isinstance(manifest, InvalidToml)
    assert str(tmp_path) not in manifest.detail


def test_clippy_config_files_are_listed_in_ascending_order(tmp_path: Path) -> None:
    (tmp_path / "crates").mkdir()
    (tmp_path / ".clippy.toml").write_text("", encoding="utf-8")
    (tmp_path / "crates" / "clippy.toml").write_text("", encoding="utf-8")
    assert gather_facts(tmp_path).clippy_config_paths == (
        PurePosixPath(".clippy.toml"),
        PurePosixPath("crates/clippy.toml"),
    )


def test_a_manifest_under_a_target_segment_is_not_a_fact(tmp_path: Path) -> None:
    """The detector must not call a manifest broken that the runner never looked at."""
    generated = tmp_path / "target" / "package" / "a-0.1.0"
    generated.mkdir(parents=True)
    (generated / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    assert gather_facts(tmp_path).cargo_manifests == {}


def test_a_manifest_in_a_directory_merely_named_like_target_is_not_excluded(tmp_path: Path) -> None:
    """The exclusion is a path-segment match, not a substring match on 'target'."""
    package = tmp_path / "my-target"
    package.mkdir()
    (package / "Cargo.toml").write_text("[package]\nname = 'a'\n", encoding="utf-8")
    facts = gather_facts(tmp_path)
    assert PurePosixPath("my-target/Cargo.toml") in facts.cargo_manifests
