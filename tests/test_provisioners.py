"""Tests for the Provisioner protocol and shared action types."""

from __future__ import annotations

import dataclasses
from typing import get_protocol_members

import pytest

from ebpy.decide.provisioner import FileAction, Provisioner


def test_provisioner_protocol_shape() -> None:
    """Provisioner exposes the four methods/attributes that every concrete tool provisioner must implement."""
    assert {"name", "packages", "config_actions", "workflow_steps"} <= get_protocol_members(Provisioner)


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
