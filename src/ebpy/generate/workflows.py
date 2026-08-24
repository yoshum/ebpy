"""The GitHub Actions workflows bootstrap writes.

Actions are pinned to commit SHAs so dependabot can bump them after ebpy has stopped
looking, and so every generated repository starts from the same place. A tag is not a
pin: whoever owns the action can move `v4` onto new code, and the repository would run
it without a diff.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import PackageManager

DEFAULT_PYTHON_VERSION = "3.12"


@dataclass(frozen=True)
class PinnedAction:
    """An action pinned to one commit, carrying the release that commit is.

    The version is a trailing comment, not the pin. Dependabot reads it to learn which
    release a SHA stands for and rewrites the two together, so they must not drift.
    """

    repository: str
    commit: str
    version: str

    @property
    def uses(self) -> str:
        return f"{self.repository}@{self.commit} # {self.version}"


CHECKOUT_ACTION = PinnedAction("actions/checkout", "11d5960a326750d5838078e36cf38b85af677262", "v4.4.0")
SETUP_PYTHON_ACTION = PinnedAction(
    "actions/setup-python", "a26af69be951a213d495a4c3e4e4022e16d87065", "v5.6.0"
)
SETUP_UV_ACTION = PinnedAction("astral-sh/setup-uv", "d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86", "v5.4.2")

# One source of truth for the run prefix, so the gate workflow and bootstrap planning cannot
# disagree on how a repository resolves its dev tools.
_RUN_PREFIXES: dict[PackageManager, str] = {
    "uv": "uv run ",
    "poetry": "poetry run ",
    "pdm": "pdm run ",
    "pipenv": "pipenv run ",
    "pip": "",
}


def run_prefix_for(manager: PackageManager) -> str:
    """Return the command prefix that resolves a dev tool under the manager (e.g. "uv run ")."""
    return _RUN_PREFIXES[manager]


@dataclass(frozen=True)
class _ManagerSteps:
    setup: list[str]
    install: str
    run_prefix: str


def _steps_for(manager: PackageManager, python_version: str) -> _ManagerSteps:
    setup_python = [
        f"      - uses: {SETUP_PYTHON_ACTION.uses}",
        "        with:",
        f'          python-version: "{python_version}"',
    ]
    run_prefix = run_prefix_for(manager)
    if manager == "uv":
        return _ManagerSteps(
            setup=[
                f"      - uses: {SETUP_UV_ACTION.uses}",
                "        with:",
                f'          python-version: "{python_version}"',
            ],
            install="uv sync --all-groups",
            run_prefix=run_prefix,
        )
    if manager == "poetry":
        return _ManagerSteps(
            setup=setup_python,
            install="pipx install poetry && poetry install",
            run_prefix=run_prefix,
        )
    if manager == "pdm":
        return _ManagerSteps(
            setup=setup_python,
            install="pipx install pdm && pdm install -d",
            run_prefix=run_prefix,
        )
    if manager == "pipenv":
        return _ManagerSteps(
            setup=setup_python,
            install="pip install pipenv && pipenv install --dev",
            run_prefix=run_prefix,
        )
    return _ManagerSteps(
        setup=setup_python,
        install="pip install ruff mypy pytest ebpy && pip install -e . || true",
        run_prefix=run_prefix,
    )


def gate_workflow(
    manager: PackageManager, tool_steps: list[str], python_version: str = DEFAULT_PYTHON_VERSION
) -> str:
    """Format check, test and the ratchet gate, on all three platforms — path handling
    breaks per platform, and only per platform. There is no raw `ruff check` or `mypy`
    step: each demands zero violations and would fail on the grandfathered backlog the
    moment the repository freezes one. `ebpy check` is the gate — it runs ruff and mypy
    through the measurement seam and fails only on findings above the ceiling. `report`
    runs after `check` with `if: always()`: the run where the gate has just failed is
    the run where the backlog is worth most."""
    steps = _steps_for(manager, python_version)
    run = steps.run_prefix
    lines = [
        "name: quality",
        "",
        "on:",
        "  push:",
        "    branches: [main]",
        "  pull_request:",
        "",
        "permissions:",
        "  contents: read",
        "",
        "jobs:",
        "  quality:",
        "    strategy:",
        "      fail-fast: false",
        "      matrix:",
        "        os: [ubuntu-latest, macos-latest, windows-latest]",
        "    runs-on: ${{ matrix.os }}",
        "    steps:",
        f"      - uses: {CHECKOUT_ACTION.uses}",
        *steps.setup,
        "      - name: Install",
        f"        run: {steps.install}",
        *tool_steps,
        "      - name: Ratchet gate",
        f"        run: {run}ebpy check",
        "      - name: Lint report",
        "        if: always()",
        f"        run: {run}ebpy report",
        "",
    ]
    return "\n".join(lines)
