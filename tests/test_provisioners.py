"""Tests for the Provisioner protocol, its file-action union, and the built-in provisioners."""

from __future__ import annotations

import dataclasses

import pytest

from ebpy.decide.bootstrap_plan import InstallAction
from ebpy.decide.provisioner import (
    AddWorkflowStep,
    AppendText,
    CreateFile,
    ProvisionContext,
    Provisioner,
    WithheldConfig,
)
from ebpy.generate import configs, workflows
from ebpy.generate.workflows import CHECKOUT_ACTION
from ebpy.models import ToolSetup
from ebpy.tools import gitleaks
from ebpy.tools.gitleaks import GitleaksProvisioner, secret_scan_workflow
from ebpy.tools.mypy import MypyProvisioner
from ebpy.tools.mypy import config as mypy_config
from ebpy.tools.mypy.config import MYPY_INI_CONTENT, MYPY_PYPROJECT_SECTION
from ebpy.tools.pytest import PytestProvisioner
from ebpy.tools.ruff import RuffProvisioner
from ebpy.tools.ruff import config as ruff_config
from ebpy.tools.ruff.config import ruff_pyproject_section, ruff_toml_content
from ebpy.tools.ruff_format import RuffFormatProvisioner
from ebpy.tools.vulture import VultureProvisioner


def _ctx(
    *, has_pyproject: bool = True, requires_python: str | None = ">=3.12", run_prefix: str = "uv run "
) -> ProvisionContext:
    return ProvisionContext(
        has_pyproject=has_pyproject, requires_python=requires_python, run_prefix=run_prefix
    )


def test_provisioner_protocol_shape() -> None:
    """Provisioner exposes exactly the name property plus the two verb-phrase planning methods."""
    assert {m for m in dir(Provisioner) if not m.startswith("_")} == {
        "name",
        "plan_packages",
        "plan_file_actions",
    }


# ---- File-action union -----------------------------------------------------


def test_create_file_is_a_frozen_dataclass() -> None:
    """CreateFile carries path/content/reason and is immutable."""
    action = CreateFile(path="ruff.toml", content="[lint]\n", reason="initial config")
    assert (action.path, action.content, action.reason) == ("ruff.toml", "[lint]\n", "initial config")
    with pytest.raises(dataclasses.FrozenInstanceError):
        action.path = "z"  # type: ignore[misc]


def test_append_text_is_a_frozen_dataclass() -> None:
    """AppendText carries path/content/reason and is immutable."""
    action = AppendText(path="pyproject.toml", content="\n[tool.x]\n", reason="section")
    assert (action.path, action.content, action.reason) == ("pyproject.toml", "\n[tool.x]\n", "section")
    with pytest.raises(dataclasses.FrozenInstanceError):
        action.content = "z"  # type: ignore[misc]


def test_add_workflow_step_is_a_frozen_dataclass() -> None:
    """AddWorkflowStep carries its step lines and is immutable."""
    action = AddWorkflowStep(lines=("      - name: Test", "        run: pytest"))
    assert action.lines == ("      - name: Test", "        run: pytest")
    with pytest.raises(dataclasses.FrozenInstanceError):
        action.lines = ()  # type: ignore[misc]


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


def test_ruff_provisioner_plan_packages_when_unconfigured() -> None:
    """Unconfigured ruff -> install the ruff package."""
    assert RuffProvisioner().plan_packages(ToolSetup(configured=False)) == ("ruff",)


def test_ruff_provisioner_plan_packages_when_configured() -> None:
    """Configured ruff -> no package install needed."""
    assert RuffProvisioner().plan_packages(ToolSetup(configured=True)) == ()


def test_ruff_provisioner_appends_config_then_adds_format_step_with_pyproject() -> None:
    """Unconfigured ruff with pyproject.toml -> append config, then always the Format check step."""
    actions = RuffProvisioner().plan_file_actions(ToolSetup(configured=False), _ctx(has_pyproject=True))
    assert actions == [
        AppendText(
            path="pyproject.toml",
            content="\n" + ruff_pyproject_section("py312"),
            reason="lint + format config; the rule tiers the ratchet will freeze",
        ),
        AddWorkflowStep(lines=("      - name: Format check", "        run: uv run ruff format --check .")),
    ]


def test_ruff_provisioner_creates_ruff_toml_then_adds_format_step_without_pyproject() -> None:
    """Unconfigured ruff without pyproject.toml -> create ruff.toml, then always the Format check step."""
    actions = RuffProvisioner().plan_file_actions(ToolSetup(configured=False), _ctx(has_pyproject=False))
    assert actions == [
        CreateFile(
            path="ruff.toml",
            content=ruff_toml_content("py312"),
            reason="lint + format config (no pyproject.toml to append to)",
        ),
        AddWorkflowStep(lines=("      - name: Format check", "        run: uv run ruff format --check .")),
    ]


def test_ruff_provisioner_translates_requires_python_into_its_own_target_version() -> None:
    """The context carries requires-python raw; spelling it as py39 is ruff's own business."""
    actions = RuffProvisioner().plan_file_actions(ToolSetup(configured=False), _ctx(requires_python=">=3.9"))
    assert isinstance(actions[0], AppendText)
    assert 'target-version = "py39"' in actions[0].content


def test_ruff_provisioner_falls_back_to_the_default_target_version_when_unspecified() -> None:
    """A repository that declares no requires-python still gets a config, at ruff's default."""
    actions = RuffProvisioner().plan_file_actions(ToolSetup(configured=False), _ctx(requires_python=None))
    assert isinstance(actions[0], AppendText)
    assert 'target-version = "py311"' in actions[0].content


def test_ruff_provisioner_configured_withholds_the_config_and_still_adds_the_format_step() -> None:
    """Configured ruff writes no config, but the text is carried so a reader can merge it by hand."""
    actions = RuffProvisioner().plan_file_actions(ToolSetup(configured=True), _ctx())
    assert actions == [
        WithheldConfig(
            AppendText(
                path="pyproject.toml",
                content="\n" + ruff_pyproject_section("py312"),
                reason="lint + format config; the rule tiers the ratchet will freeze",
            ),
            "ruff is already configured",
        ),
        AddWorkflowStep(lines=("      - name: Format check", "        run: uv run ruff format --check .")),
    ]


def test_ruff_provisioner_format_step_follows_the_run_prefix() -> None:
    """An empty run_prefix (plain pip layout) drops the prefix from the Format check command."""
    actions = RuffProvisioner().plan_file_actions(ToolSetup(configured=True), _ctx(run_prefix=""))
    assert actions[-1] == AddWorkflowStep(
        lines=("      - name: Format check", "        run: ruff format --check .")
    )


def test_a_withheld_ruff_config_names_the_file_it_would_have_gone_into() -> None:
    """Without a pyproject.toml the config bootstrap holds back is the standalone ruff.toml."""
    actions = RuffProvisioner().plan_file_actions(ToolSetup(configured=True), _ctx(has_pyproject=False))
    withheld = next(a for a in actions if isinstance(a, WithheldConfig))
    assert withheld.would_have.path == "ruff.toml"
    assert withheld.would_have.content == ruff_toml_content("py312")


# ---- RuffFormatProvisioner -------------------------------------------------


def test_ruff_format_provisioner_name_is_formatter() -> None:
    """RuffFormatProvisioner advertises the canonical tool name."""
    assert RuffFormatProvisioner().name == "formatter"


def test_ruff_format_provisioner_plan_packages_always_empty() -> None:
    """RuffFormatProvisioner never requests package installs: ruff covers formatting."""
    assert RuffFormatProvisioner().plan_packages(ToolSetup(configured=False)) == ()
    assert RuffFormatProvisioner().plan_packages(ToolSetup(configured=True)) == ()


def test_ruff_format_provisioner_plan_file_actions_always_empty() -> None:
    """RuffFormatProvisioner contributes nothing: config and Format step belong to RuffProvisioner."""
    assert RuffFormatProvisioner().plan_file_actions(ToolSetup(configured=False), _ctx()) == []
    assert (
        RuffFormatProvisioner().plan_file_actions(ToolSetup(configured=True), _ctx(has_pyproject=False)) == []
    )


# ---- MypyProvisioner -------------------------------------------------------


def test_mypy_provisioner_name_is_mypy() -> None:
    """MypyProvisioner advertises the canonical tool name."""
    assert MypyProvisioner().name == "mypy"


def test_mypy_provisioner_plan_packages_when_unconfigured() -> None:
    """Unconfigured mypy -> install the mypy package."""
    assert MypyProvisioner().plan_packages(ToolSetup(configured=False)) == ("mypy",)


def test_mypy_provisioner_plan_packages_when_configured() -> None:
    """Configured mypy -> no package install needed."""
    assert MypyProvisioner().plan_packages(ToolSetup(configured=True)) == ()


def test_mypy_provisioner_appends_to_pyproject_when_present() -> None:
    """Unconfigured mypy with pyproject.toml -> append a section, no gate step."""
    actions = MypyProvisioner().plan_file_actions(ToolSetup(configured=False), _ctx(has_pyproject=True))
    assert actions == [
        AppendText(
            path="pyproject.toml",
            content="\n" + MYPY_PYPROJECT_SECTION,
            reason="type checking, strict — errors are ratcheted per file per rule, like Ruff's",
        )
    ]


def test_mypy_provisioner_creates_mypy_ini_without_pyproject() -> None:
    """Unconfigured mypy without pyproject.toml -> create mypy.ini, no gate step."""
    actions = MypyProvisioner().plan_file_actions(ToolSetup(configured=False), _ctx(has_pyproject=False))
    assert actions == [
        CreateFile(
            path="mypy.ini",
            content=MYPY_INI_CONTENT,
            reason="type checking, strict (no pyproject.toml to append to)",
        )
    ]


def test_configured_mypy_installs_nothing_and_withholds_its_config() -> None:
    """Configured mypy -> no packages, and the config it would have written, carried not written."""
    assert MypyProvisioner().plan_packages(ToolSetup(configured=True)) == ()
    assert MypyProvisioner().plan_file_actions(ToolSetup(configured=True), _ctx()) == [
        WithheldConfig(
            AppendText(
                path="pyproject.toml",
                content="\n" + MYPY_PYPROJECT_SECTION,
                reason="type checking, strict — errors are ratcheted per file per rule, like Ruff's",
            ),
            "mypy is already configured",
        )
    ]


# ---- PytestProvisioner -----------------------------------------------------


def test_pytest_provisioner_name_is_pytest() -> None:
    """PytestProvisioner advertises the canonical tool name."""
    assert PytestProvisioner().name == "pytest"


def test_pytest_provisioner_plan_packages_when_unconfigured() -> None:
    """Unconfigured pytest -> install the pytest package."""
    assert PytestProvisioner().plan_packages(ToolSetup(configured=False)) == ("pytest",)


def test_pytest_provisioner_plan_packages_when_configured() -> None:
    """Configured pytest -> no package install needed."""
    assert PytestProvisioner().plan_packages(ToolSetup(configured=True)) == ()


def test_pytest_provisioner_always_adds_the_test_step() -> None:
    """Pytest emits exactly the Test gate step regardless of setup, following the run prefix."""
    for configured in (False, True):
        actions = PytestProvisioner().plan_file_actions(ToolSetup(configured=configured), _ctx())
        assert actions == [AddWorkflowStep(lines=("      - name: Test", "        run: uv run pytest"))]


def test_pytest_provisioner_test_step_with_empty_prefix() -> None:
    """An empty run_prefix (plain pip layout) drops the prefix from the Test command."""
    actions = PytestProvisioner().plan_file_actions(ToolSetup(configured=False), _ctx(run_prefix=""))
    assert actions == [AddWorkflowStep(lines=("      - name: Test", "        run: pytest"))]


# ---- VultureProvisioner ----------------------------------------------------


def test_vulture_provisioner_name_is_vulture() -> None:
    """VultureProvisioner advertises the canonical tool name."""
    assert VultureProvisioner().name == "vulture"


def test_vulture_provisioner_plan_packages_when_unconfigured() -> None:
    """Unconfigured vulture -> install the vulture package."""
    assert VultureProvisioner().plan_packages(ToolSetup(configured=False)) == ("vulture",)


def test_vulture_provisioner_plan_packages_when_configured() -> None:
    """Configured vulture -> no package install needed."""
    assert VultureProvisioner().plan_packages(ToolSetup(configured=True)) == ()


def test_vulture_provisioner_plan_file_actions_always_empty() -> None:
    """Vulture has no generated config and no gate step today."""
    assert VultureProvisioner().plan_file_actions(ToolSetup(configured=False), _ctx()) == []
    assert VultureProvisioner().plan_file_actions(ToolSetup(configured=True), _ctx(has_pyproject=False)) == []


# ---- GitleaksProvisioner ---------------------------------------------------


def test_gitleaks_provisioner_name_is_secret_scan() -> None:
    """GitleaksProvisioner advertises the canonical tool name for the registry slot."""
    assert GitleaksProvisioner().name == "secret-scan"


def test_gitleaks_provisioner_plan_packages_always_empty() -> None:
    """Gitleaks is not a Python package dependency — never any packages to install."""
    assert GitleaksProvisioner().plan_packages(ToolSetup(configured=False)) == ()
    assert GitleaksProvisioner().plan_packages(ToolSetup(configured=True)) == ()


def test_gitleaks_provisioner_creates_the_secret_scan_workflow_unconditionally() -> None:
    """Gitleaks owns secret-scan.yml outright and proposes it regardless of setup."""
    expected = CreateFile(
        path=".github/workflows/secret-scan.yml",
        content=secret_scan_workflow(),
        reason="gitleaks over history and working tree — the one check with no baseline",
    )
    for configured in (False, True):
        assert GitleaksProvisioner().plan_file_actions(ToolSetup(configured=configured), _ctx()) == [expected]


def test_gitleaks_knowledge_lives_only_under_tools() -> None:
    """Concrete gitleaks knowledge sits under tools/, never in the generic workflows module."""
    for attr in ("secret_scan_workflow", "GITLEAKS_VERSION", "GITLEAKS_SHA256"):
        assert not hasattr(workflows, attr), f"{attr} must not live in generate.workflows"
        assert hasattr(gitleaks, attr), f"{attr} must live in tools.gitleaks"


def test_the_gitleaks_workflow_uses_the_generic_checkout_pin() -> None:
    """The gitleaks workflow reuses the generic CHECKOUT_ACTION pin kept in generate.workflows."""
    assert CHECKOUT_ACTION.uses in secret_scan_workflow()


# ---- Where tool knowledge lives --------------------------------------------


def test_ruff_config_knowledge_lives_only_under_tools() -> None:
    """Concrete ruff config knowledge sits under tools/, never in the generic configs module."""
    for attr in ("ruff_pyproject_section", "ruff_toml_content", "ruff_target_version"):
        assert not hasattr(configs, attr), f"{attr} must not live in generate.configs"
        assert hasattr(ruff_config, attr), f"{attr} must live in tools.ruff.config"


def test_mypy_config_knowledge_lives_only_under_tools() -> None:
    """Concrete mypy config knowledge sits under tools/, never in the generic configs module."""
    for attr in ("MYPY_PYPROJECT_SECTION", "MYPY_INI_CONTENT"):
        assert not hasattr(configs, attr), f"{attr} must not live in generate.configs"
        assert hasattr(mypy_config, attr), f"{attr} must live in tools.mypy.config"


def test_the_provision_context_carries_requires_python_raw() -> None:
    """The shared context holds the repository's own declaration, not ruff's spelling of it."""
    fields = {f.name for f in dataclasses.fields(ProvisionContext)}
    assert "requires_python" in fields
    assert "target_version" not in fields, "a ruff-only dialect must not reappear in the shared context"
