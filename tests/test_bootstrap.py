from __future__ import annotations

import tomllib
from pathlib import Path

from ebpy.decide.bootstrap_plan import BootstrapPlan, build_plan, render_plan
from ebpy.decide.diagnose import diagnose
from ebpy.generate.configs import (
    DEPENDABOT_CONTENT,
    python_version_from_requires,
    ruff_pyproject_section,
    ruff_toml_content,
)
from ebpy.generate.workflows import (
    GITLEAKS_SHA256,
    PinnedAction,
    gate_workflow,
    secret_scan_workflow,
)
from ebpy.models import WorkflowFile
from ebpy.repo.detect.ci import unpinned_actions
from ebpy.repo.facts import gather_facts


def plan_for(tmp_path: Path) -> BootstrapPlan:
    facts = gather_facts(tmp_path)
    return build_plan(diagnose(facts, ()), facts.root_entries, facts.all_files, "3.12")


def test_the_target_version_follows_requires_python() -> None:
    assert python_version_from_requires(">=3.12") == "py312"
    assert python_version_from_requires(">=3.9,<4") == "py39"
    assert python_version_from_requires(None) == "py311"
    assert python_version_from_requires("nonsense") == "py311"


def test_the_generated_ruff_config_parses_as_toml() -> None:
    parsed = tomllib.loads(ruff_pyproject_section("py312"))
    assert parsed["tool"]["ruff"]["target-version"] == "py312"
    assert "C90" in parsed["tool"]["ruff"]["lint"]["select"]
    assert parsed["tool"]["ruff"]["lint"]["mccabe"]["max-complexity"] == 10


def test_a_standalone_ruff_toml_carries_no_tool_prefix() -> None:
    parsed = tomllib.loads(ruff_toml_content("py311"))
    assert "tool" not in parsed
    assert parsed["lint"]["mccabe"]["max-complexity"] == 10


def test_gate_workflow_uv_full_text() -> None:
    """Pins the full gate_workflow("uv") output so any content change surfaces immediately."""
    expected = (
        "name: quality\n"
        "\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "  pull_request:\n"
        "\n"
        "permissions:\n"
        "  contents: read\n"
        "\n"
        "jobs:\n"
        "  quality:\n"
        "    strategy:\n"
        "      fail-fast: false\n"
        "      matrix:\n"
        "        os: [ubuntu-latest, macos-latest, windows-latest]\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    steps:\n"
        "      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0\n"
        "      - uses: astral-sh/setup-uv@d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86 # v5.4.2\n"
        "        with:\n"
        '          python-version: "3.12"\n'
        "      - name: Install\n"
        "        run: uv sync --all-groups\n"
        "      - name: Format check\n"
        "        run: uv run ruff format --check .\n"
        "      - name: Test\n"
        "        run: uv run pytest\n"
        "      - name: Ratchet gate\n"
        "        run: uv run ebpy check\n"
        "      - name: Lint report\n"
        "        if: always()\n"
        "        run: uv run ebpy report\n"
    )
    assert gate_workflow("uv") == expected


def test_the_gate_workflow_runs_the_ratchet_on_three_platforms() -> None:
    workflow = gate_workflow("uv")
    assert "ubuntu-latest, macos-latest, windows-latest" in workflow
    assert "uv run ebpy check" in workflow
    # The run where the gate has just failed is the run where the backlog is worth most.
    assert "if: always()" in workflow


def test_the_workflow_follows_the_repositorys_own_package_manager() -> None:
    assert "poetry run ebpy check" in gate_workflow("poetry")
    assert "pdm run pytest" in gate_workflow("pdm")


def test_the_secret_workflow_scans_history_and_working_tree() -> None:
    workflow = secret_scan_workflow()
    # A shallow clone misses the commit that leaked.
    assert "fetch-depth: 0" in workflow
    assert "gitleaks git ." in workflow
    assert "gitleaks dir ." in workflow
    # The secret must not land in a public log.
    assert "--redact" in workflow


def test_every_generated_action_is_pinned_to_a_commit() -> None:
    """What bootstrap writes must not trip the gap diagnose reports."""
    for manager in ("uv", "poetry", "pdm", "pipenv", "pip"):
        workflows = (
            WorkflowFile(path="quality.yml", content=gate_workflow(manager)),
            WorkflowFile(path="secret-scan.yml", content=secret_scan_workflow()),
        )
        assert unpinned_actions(workflows) == ()


def test_the_pinned_version_is_a_comment_beside_the_commit() -> None:
    # Dependabot rewrites the pair together, so the release has to travel with the SHA.
    action = PinnedAction("actions/checkout", "a" * 40, "v4.4.0")
    assert action.uses == f"actions/checkout@{'a' * 40} # v4.4.0"


def test_the_secret_workflow_checks_the_digest_before_it_runs_the_binary() -> None:
    workflow = secret_scan_workflow()
    assert GITLEAKS_SHA256 in workflow
    # Order is the whole point: a digest checked after extraction has verified nothing.
    verify = workflow.index("sha256sum -c")
    assert verify < workflow.index("tar -xzf")
    assert verify < workflow.index("install -m 0755")


def test_dependabot_updates_the_actions_bootstrap_just_pinned() -> None:
    # Pinning without an updater freezes the repo on whatever was current that day.
    assert "github-actions" in DEPENDABOT_CONTENT


def test_a_bare_repository_gets_configs_and_a_dev_install(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    plan = plan_for(tmp_path)
    assert plan.install is not None
    assert set(plan.install.packages) == {"ruff", "mypy", "pytest", "vulture"}
    written = {action.path for action in plan.files}
    assert written == {
        "ruff.toml",
        "mypy.ini",
        ".github/workflows/quality.yml",
        ".github/workflows/secret-scan.yml",
        ".github/dependabot.yml",
        ".gitattributes",
    }


def test_configs_are_appended_to_an_existing_pyproject_rather_than_a_new_file(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "app"\n', encoding="utf-8")
    plan = plan_for(tmp_path)
    appends = [action for action in plan.files if action.mode == "append"]
    assert {action.path for action in appends} == {"pyproject.toml"}
    assert "ruff.toml" not in {action.path for action in plan.files}


def test_the_mypy_config_reason_describes_per_cell_ratcheting_not_a_counter(tmp_path: Path) -> None:
    """The reason printed beside the mypy config must describe today's model — errors ratcheted per
    file per rule like Ruff's — not the retired global "counter". Pinned so the wording cannot drift
    back without a failing test."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "app"\n', encoding="utf-8")
    plan = plan_for(tmp_path)
    mypy_action = next(action for action in plan.files if "type checking" in action.reason)
    assert "per file per rule" in mypy_action.reason
    assert "counter" not in mypy_action.reason


def test_an_existing_config_is_never_overwritten(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows" / "quality.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: ours\n", encoding="utf-8")
    plan = plan_for(tmp_path)
    assert ".github/workflows/quality.yml" not in {a.path for a in plan.files}
    assert any("quality.yml" in note for note in plan.skipped)


def test_a_dry_run_says_what_it_would_do_and_nothing_else(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    rendered = render_plan(plan_for(tmp_path), dry_run=True)
    assert "would run:" in rendered
    assert "would write" in rendered
    assert "Next:" not in rendered
