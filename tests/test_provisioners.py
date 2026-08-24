"""Tests for the Provisioner protocol, shared action types, and the three built-in provisioners."""

from __future__ import annotations

import dataclasses

import pytest

from ebpy.decide.provisioner import FileAction, InstallAction, Provisioner
from ebpy.generate.configs import (
    MYPY_INI_CONTENT,
    MYPY_PYPROJECT_SECTION,
    ruff_pyproject_section,
    ruff_toml_content,
)
from ebpy.models import ToolSetup
from ebpy.tools.gitleaks import GitleaksProvisioner
from ebpy.tools.mypy import MypyProvisioner
from ebpy.tools.pytest import PytestProvisioner
from ebpy.tools.ruff import RuffProvisioner
from ebpy.tools.ruff_format import RuffFormatProvisioner
from ebpy.tools.vulture import VultureProvisioner


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


# ---- RuffProvisioner -------------------------------------------------------


def test_ruff_provisioner_name_is_ruff() -> None:
    """RuffProvisioner advertises the canonical tool name."""
    assert RuffProvisioner().name == "ruff"


def test_ruff_provisioner_packages_when_unconfigured() -> None:
    """Unconfigured ruff -> install the ruff package."""
    assert RuffProvisioner().packages(ToolSetup(configured=False)) == ("ruff",)


def test_ruff_provisioner_packages_when_configured() -> None:
    """Configured ruff -> no package install needed."""
    assert RuffProvisioner().packages(ToolSetup(configured=True)) == ()


def test_ruff_provisioner_appends_to_pyproject_when_present() -> None:
    """Unconfigured ruff with pyproject.toml -> append a section to pyproject.toml."""
    actions = RuffProvisioner().config_actions(
        ToolSetup(configured=False), has_pyproject=True, target_version="py312"
    )
    assert len(actions) == 1
    assert actions[0].path == "pyproject.toml"
    assert actions[0].mode == "append"


def test_ruff_provisioner_append_content_and_reason_match_bootstrap_plan() -> None:
    """Appended content and reason reproduce bootstrap_plan._config_actions verbatim."""
    actions = RuffProvisioner().config_actions(
        ToolSetup(configured=False), has_pyproject=True, target_version="py312"
    )
    assert actions[0].content == "\n" + ruff_pyproject_section("py312")
    assert actions[0].reason == "lint + format config; the rule tiers the ratchet will freeze"


def test_ruff_provisioner_writes_ruff_toml_without_pyproject() -> None:
    """Unconfigured ruff without pyproject.toml -> create ruff.toml."""
    actions = RuffProvisioner().config_actions(
        ToolSetup(configured=False), has_pyproject=False, target_version="py312"
    )
    assert len(actions) == 1
    assert actions[0].path == "ruff.toml"
    assert actions[0].mode == "create"


def test_ruff_provisioner_create_content_and_reason_match_bootstrap_plan() -> None:
    """Created ruff.toml content and reason reproduce bootstrap_plan._config_actions verbatim."""
    actions = RuffProvisioner().config_actions(
        ToolSetup(configured=False), has_pyproject=False, target_version="py312"
    )
    assert actions[0].content == ruff_toml_content("py312")
    assert actions[0].reason == "lint + format config (no pyproject.toml to append to)"


def test_configured_ruff_needs_no_packages_or_config() -> None:
    """Configured ruff -> no packages, no config actions."""
    assert RuffProvisioner().packages(ToolSetup(configured=True)) == ()
    assert RuffProvisioner().config_actions(ToolSetup(configured=True), True, "py312") == []


def test_ruff_provisioner_workflow_steps_match_gate_workflow() -> None:
    """workflow_steps emits the Format check step lines matching gate_workflow output exactly."""
    steps = RuffProvisioner().workflow_steps("uv run ")
    assert steps == [
        "      - name: Format check",
        "        run: uv run ruff format --check .",
    ]


def test_ruff_provisioner_workflow_steps_with_empty_prefix() -> None:
    """workflow_steps works with an empty run_prefix (plain pip install layout)."""
    steps = RuffProvisioner().workflow_steps("")
    assert steps[1] == "        run: ruff format --check ."


# ---- RuffFormatProvisioner -------------------------------------------------


def test_ruff_format_provisioner_name_is_formatter() -> None:
    """RuffFormatProvisioner advertises the canonical tool name."""
    assert RuffFormatProvisioner().name == "formatter"


def test_ruff_format_provisioner_packages_always_empty() -> None:
    """RuffFormatProvisioner never requests package installs: ruff covers formatting."""
    assert RuffFormatProvisioner().packages(ToolSetup(configured=False)) == ()
    assert RuffFormatProvisioner().packages(ToolSetup(configured=True)) == ()


def test_ruff_format_provisioner_config_actions_always_empty() -> None:
    """RuffFormatProvisioner never writes config files: ruff.toml already includes format settings."""
    assert RuffFormatProvisioner().config_actions(ToolSetup(configured=False), True, "py312") == []
    assert RuffFormatProvisioner().config_actions(ToolSetup(configured=True), False, "py312") == []


def test_ruff_format_provisioner_workflow_steps_always_empty() -> None:
    """RuffFormatProvisioner has no CI steps: the Format check step belongs to RuffProvisioner."""
    assert RuffFormatProvisioner().workflow_steps("uv run ") == []


# ---- MypyProvisioner -------------------------------------------------------


def test_mypy_provisioner_name_is_mypy() -> None:
    """MypyProvisioner advertises the canonical tool name."""
    assert MypyProvisioner().name == "mypy"


def test_mypy_provisioner_packages_when_unconfigured() -> None:
    """Unconfigured mypy -> install the mypy package."""
    assert MypyProvisioner().packages(ToolSetup(configured=False)) == ("mypy",)


def test_mypy_provisioner_packages_when_configured() -> None:
    """Configured mypy -> no package install needed."""
    assert MypyProvisioner().packages(ToolSetup(configured=True)) == ()


def test_mypy_provisioner_appends_to_pyproject_when_present() -> None:
    """Unconfigured mypy with pyproject.toml -> append a section to pyproject.toml."""
    actions = MypyProvisioner().config_actions(
        ToolSetup(configured=False), has_pyproject=True, target_version="py312"
    )
    assert len(actions) == 1
    assert actions[0].path == "pyproject.toml"
    assert actions[0].mode == "append"


def test_mypy_provisioner_append_content_and_reason_match_bootstrap_plan() -> None:
    """Appended content and reason reproduce bootstrap_plan._config_actions verbatim."""
    actions = MypyProvisioner().config_actions(
        ToolSetup(configured=False), has_pyproject=True, target_version="py312"
    )
    assert actions[0].content == "\n" + MYPY_PYPROJECT_SECTION
    assert actions[0].reason == "type checking, strict — errors are ratcheted per file per rule, like Ruff's"


def test_mypy_provisioner_writes_mypy_ini_without_pyproject() -> None:
    """Unconfigured mypy without pyproject.toml -> create mypy.ini."""
    actions = MypyProvisioner().config_actions(
        ToolSetup(configured=False), has_pyproject=False, target_version="py312"
    )
    assert len(actions) == 1
    assert actions[0].path == "mypy.ini"
    assert actions[0].mode == "create"


def test_mypy_provisioner_create_content_and_reason_match_bootstrap_plan() -> None:
    """Created mypy.ini content and reason reproduce bootstrap_plan._config_actions verbatim."""
    actions = MypyProvisioner().config_actions(
        ToolSetup(configured=False), has_pyproject=False, target_version="py312"
    )
    assert actions[0].content == MYPY_INI_CONTENT
    assert actions[0].reason == "type checking, strict (no pyproject.toml to append to)"


def test_configured_mypy_needs_no_packages_or_config() -> None:
    """Configured mypy -> no packages, no config actions."""
    assert MypyProvisioner().packages(ToolSetup(configured=True)) == ()
    assert MypyProvisioner().config_actions(ToolSetup(configured=True), True, "py312") == []


def test_mypy_provisioner_workflow_steps_always_empty() -> None:
    """Type checking runs through ebpy check, not a raw mypy CI step."""
    assert MypyProvisioner().workflow_steps("uv run ") == []
    assert MypyProvisioner().workflow_steps("") == []


# ---- PytestProvisioner -----------------------------------------------------


def test_pytest_provisioner_name_is_pytest() -> None:
    """PytestProvisioner advertises the canonical tool name."""
    assert PytestProvisioner().name == "pytest"


def test_pytest_provisioner_packages_when_unconfigured() -> None:
    """Unconfigured pytest -> install the pytest package."""
    assert PytestProvisioner().packages(ToolSetup(configured=False)) == ("pytest",)


def test_pytest_provisioner_packages_when_configured() -> None:
    """Configured pytest -> no package install needed."""
    assert PytestProvisioner().packages(ToolSetup(configured=True)) == ()


def test_pytest_provisioner_config_actions_always_empty() -> None:
    """Pytest requires no generated configuration — never any file actions."""
    assert PytestProvisioner().config_actions(ToolSetup(configured=False), True, "py312") == []
    assert PytestProvisioner().config_actions(ToolSetup(configured=True), False, "py312") == []


def test_pytest_provisioner_workflow_steps_match_gate_workflow() -> None:
    """workflow_steps emits the Test step lines matching gate_workflow output exactly."""
    steps = PytestProvisioner().workflow_steps("uv run ")
    assert steps == [
        "      - name: Test",
        "        run: uv run pytest",
    ]


def test_pytest_provisioner_workflow_steps_with_empty_prefix() -> None:
    """workflow_steps works with an empty run_prefix (plain pip install layout)."""
    steps = PytestProvisioner().workflow_steps("")
    assert steps == [
        "      - name: Test",
        "        run: pytest",
    ]


# ---- VultureProvisioner ----------------------------------------------------


def test_vulture_provisioner_name_is_vulture() -> None:
    """VultureProvisioner advertises the canonical tool name."""
    assert VultureProvisioner().name == "vulture"


def test_vulture_provisioner_packages_when_unconfigured() -> None:
    """Unconfigured vulture -> install the vulture package."""
    assert VultureProvisioner().packages(ToolSetup(configured=False)) == ("vulture",)


def test_vulture_provisioner_packages_when_configured() -> None:
    """Configured vulture -> no package install needed."""
    assert VultureProvisioner().packages(ToolSetup(configured=True)) == ()


def test_vulture_provisioner_config_actions_always_empty() -> None:
    """Vulture has no generated configuration today."""
    assert VultureProvisioner().config_actions(ToolSetup(configured=False), True, "py312") == []
    assert VultureProvisioner().config_actions(ToolSetup(configured=True), False, "py312") == []


def test_vulture_provisioner_workflow_steps_always_empty() -> None:
    """Vulture has no gate CI step today."""
    assert VultureProvisioner().workflow_steps("uv run ") == []
    assert VultureProvisioner().workflow_steps("") == []


# ---- GitleaksProvisioner ---------------------------------------------------


def test_gitleaks_provisioner_name_is_secret_scan() -> None:
    """GitleaksProvisioner advertises the canonical tool name for the registry slot."""
    assert GitleaksProvisioner().name == "secret-scan"


def test_gitleaks_provisioner_packages_always_empty() -> None:
    """Gitleaks is not a Python package dependency — never any packages to install."""
    assert GitleaksProvisioner().packages(ToolSetup(configured=False)) == ()
    assert GitleaksProvisioner().packages(ToolSetup(configured=True)) == ()


def test_gitleaks_provisioner_config_actions_always_empty() -> None:
    """secret-scan.yml is created at the bootstrap level, not via config_actions."""
    assert GitleaksProvisioner().config_actions(ToolSetup(configured=False), True, "py312") == []
    assert GitleaksProvisioner().config_actions(ToolSetup(configured=True), False, "py312") == []


def test_gitleaks_provisioner_workflow_steps_always_empty() -> None:
    """Gitleaks runs as a standalone workflow, not as a gate step."""
    assert GitleaksProvisioner().workflow_steps("uv run ") == []
    assert GitleaksProvisioner().workflow_steps("") == []
