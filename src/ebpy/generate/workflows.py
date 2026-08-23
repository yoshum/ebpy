"""The GitHub Actions workflows bootstrap writes.

Actions are pinned to commit SHAs so dependabot can bump them after ebpy has stopped
looking, and so every generated repository starts from the same place. A tag is not a
pin: whoever owns the action can move `v4` onto new code, and the repository would run
it without a diff.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import chain

from ..models import PackageManager
from ..tools import PROVISIONERS

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

# The MIT CLI rather than gitleaks-action, which needs a licence key under a GitHub
# Organization. Verified against a digest below, because a release asset can be replaced
# in place under the same tag — and it is this binary that decides whether a leaked
# credential gets reported.
GITLEAKS_VERSION = "8.30.1"
GITLEAKS_SHA256 = "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"


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
    if manager == "uv":
        return _ManagerSteps(
            setup=[
                f"      - uses: {SETUP_UV_ACTION.uses}",
                "        with:",
                f'          python-version: "{python_version}"',
            ],
            install="uv sync --all-groups",
            run_prefix="uv run ",
        )
    if manager == "poetry":
        return _ManagerSteps(
            setup=setup_python,
            install="pipx install poetry && poetry install",
            run_prefix="poetry run ",
        )
    if manager == "pdm":
        return _ManagerSteps(
            setup=setup_python,
            install="pipx install pdm && pdm install -d",
            run_prefix="pdm run ",
        )
    if manager == "pipenv":
        return _ManagerSteps(
            setup=setup_python,
            install="pip install pipenv && pipenv install --dev",
            run_prefix="pipenv run ",
        )
    return _ManagerSteps(
        setup=setup_python,
        install="pip install ruff mypy pytest ebpy && pip install -e . || true",
        run_prefix="",
    )


def gate_workflow(manager: PackageManager, python_version: str = DEFAULT_PYTHON_VERSION) -> str:
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
        *chain.from_iterable(p.workflow_steps(run) for p in PROVISIONERS),
        "      - name: Ratchet gate",
        f"        run: {run}ebpy check",
        "      - name: Lint report",
        "        if: always()",
        f"        run: {run}ebpy report",
        "",
    ]
    return "\n".join(lines)


def secret_scan_workflow() -> str:
    """fetch-depth: 0 because a shallow clone misses the commit that leaked, and
    --redact so the secret does not land in a public log."""
    head = f"""\
name: secret-scan

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: {CHECKOUT_ACTION.uses}
        with:
          fetch-depth: 0
      - name: Install gitleaks
        env:
          GITLEAKS_VERSION: "{GITLEAKS_VERSION}"
          GITLEAKS_SHA256: "{GITLEAKS_SHA256}"
"""
    # Not an f-string: every ${...} below is expanded by bash on the runner, and an
    # f-string would eat them here instead. set -euo pipefail rather than trusting the
    # runner's default flags, so the digest check cannot be lost inside a pipeline.
    install = """\
        run: |
          set -euo pipefail
          curl -sSfL -o gitleaks.tar.gz \\
            "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
          echo "${GITLEAKS_SHA256}  gitleaks.tar.gz" | sha256sum -c -
          tar -xzf gitleaks.tar.gz gitleaks
          install -m 0755 gitleaks /usr/local/bin/gitleaks
      - name: Scan history
        run: gitleaks git . --redact --exit-code 2
      - name: Scan working tree
        run: gitleaks dir . --redact --exit-code 2
"""
    return head + install
