"""Tests for store/config.py: reading and validating .ebpy/config.json."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from ebpy.errors import CommandError
from ebpy.store.config import read_config

if TYPE_CHECKING:
    from pathlib import Path


def _write(cwd: Path, obj: object) -> None:
    (cwd / ".ebpy").mkdir(parents=True, exist_ok=True)
    (cwd / ".ebpy" / "config.json").write_text(json.dumps(obj), encoding="utf-8")


def test_absent_config_reads_as_none(tmp_path: Path) -> None:
    """Absent config file returns None, not an error."""
    assert read_config(tmp_path) is None


def test_valid_config_reads_declared_analyzers(tmp_path: Path) -> None:
    """Valid config returns EbpyConfig with sorted, deduped analyzers."""
    _write(tmp_path, {"version": 1, "analyzers": ["mypy", "ruff"]})
    cfg = read_config(tmp_path)
    assert cfg is not None
    assert cfg.analyzers == ("mypy", "ruff")


def test_duplicate_analyzers_are_deduped_and_sorted(tmp_path: Path) -> None:
    """Duplicate analyzer names are deduped and the result is sorted."""
    _write(tmp_path, {"version": 1, "analyzers": ["ruff", "mypy", "ruff"]})
    cfg = read_config(tmp_path)
    assert cfg is not None
    assert cfg.analyzers == ("mypy", "ruff")


def test_unknown_analyzer_name_is_rejected(tmp_path: Path) -> None:
    """Analyzer names not in ANALYZER_NAMES are rejected with the unknown name in the message."""
    _write(tmp_path, {"version": 1, "analyzers": ["ruff", "pylint"]})
    with pytest.raises(CommandError, match="pylint"):
        read_config(tmp_path)


def test_wrong_version_is_rejected(tmp_path: Path) -> None:
    """A config with an unrecognised version field raises CommandError mentioning 'version'."""
    _write(tmp_path, {"version": 2, "analyzers": ["ruff"]})
    with pytest.raises(CommandError, match="version"):
        read_config(tmp_path)


def test_empty_analyzers_is_rejected(tmp_path: Path) -> None:
    """An explicit empty analyzers list is rejected — it is not the same as absent config."""
    _write(tmp_path, {"version": 1, "analyzers": []})
    with pytest.raises(CommandError, match="at least one"):
        read_config(tmp_path)


def test_non_dict_config_is_rejected(tmp_path: Path) -> None:
    """A config that is not a JSON object is rejected (version check catches it)."""
    _write(tmp_path, ["analyzers", "ruff"])
    with pytest.raises(CommandError, match="version"):
        read_config(tmp_path)


def test_analyzers_not_a_list_is_rejected(tmp_path: Path) -> None:
    """A config with a non-list 'analyzers' value raises CommandError."""
    _write(tmp_path, {"version": 1, "analyzers": "ruff"})
    with pytest.raises(CommandError):
        read_config(tmp_path)


def test_invalid_json_raises_command_error(tmp_path: Path) -> None:
    """A config file that contains invalid JSON raises CommandError."""
    (tmp_path / ".ebpy").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ebpy" / "config.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(CommandError):
        read_config(tmp_path)
