"""Tests for the Provisioner protocol and shared action types."""

from __future__ import annotations

import dataclasses

import pytest

from ebpy.decide.provisioner import FileAction, InstallAction, Provisioner


def test_provisioner_protocol_shape() -> None:
    """Provisioner exposes the four methods/attributes that every concrete tool provisioner must implement."""
    assert {m for m in dir(Provisioner) if not m.startswith("_")} == {
        "name",
        "packages",
        "config_actions",
        "workflow_steps",
    }


def test_file_action_is_a_frozen_dataclass() -> None:
    """FileAction carries all four fields and can be round-tripped."""
    action = FileAction(path="ruff.toml", content="[lint]\n", mode="create", reason="initial config")
    assert action.path == "ruff.toml"
    assert action.content == "[lint]\n"
    assert action.mode == "create"
    assert action.reason == "initial config"


def test_file_action_is_immutable() -> None:
    """FileAction must be frozen — mutation raises FrozenInstanceError."""
    action = FileAction(path="x", content="y", mode="append", reason="r")
    with pytest.raises(dataclasses.FrozenInstanceError):
        action.path = "z"  # type: ignore[misc]


def test_install_action_is_a_frozen_dataclass_with_tuple_fields() -> None:
    """InstallAction carries both tuple fields and can be round-tripped."""
    action = InstallAction(packages=("ruff",), argv=("uv", "add", "--dev", "ruff"))
    assert action.packages == ("ruff",)
    assert action.argv == ("uv", "add", "--dev", "ruff")


def test_install_action_is_immutable() -> None:
    """InstallAction must be frozen — mutation raises FrozenInstanceError."""
    action = InstallAction(packages=("ruff",), argv=("uv", "add", "--dev", "ruff"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        action.packages = ("mypy",)  # type: ignore[misc]
