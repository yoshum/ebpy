"""The GitHub Actions workflows bootstrap writes.

Action versions are pinned constants so dependabot can bump them after ebpy has
stopped looking, and so every generated repository starts from the same place.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import PackageManager

DEFAULT_PYTHON_VERSION = "3.12"

CHECKOUT_ACTION = "actions/checkout@v4"
SETUP_PYTHON_ACTION = "actions/setup-python@v5"
SETUP_UV_ACTION = "astral-sh/setup-uv@v5"

# Pinned gitleaks release, downloaded checksum-verified in the workflow below. The MIT
# CLI rather than gitleaks-action, which needs a licence key under a GitHub Organization.
GITLEAKS_VERSION = "8.30.1"


@dataclass(frozen=True)
class _ManagerSteps:
    setup: list[str]
    install: str
    run_prefix: str


def _steps_for(manager: PackageManager, python_version: str) -> _ManagerSteps:
    setup_python = [
        f"      - uses: {SETUP_PYTHON_ACTION}",
        "        with:",
        f'          python-version: "{python_version}"',
    ]
    if manager == "uv":
        return _ManagerSteps(
            setup=[
                f"      - uses: {SETUP_UV_ACTION}",
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
    """Lint, typecheck, test and the ratchet gate, on all three platforms — path
    handling breaks per platform, and only per platform. `report` runs after `check`
    with `if: always()`: the run where the gate has just failed is the run where the
    backlog is worth most."""
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
        f"      - uses: {CHECKOUT_ACTION}",
        *steps.setup,
        "      - name: Install",
        f"        run: {steps.install}",
        "      - name: Format check",
        f"        run: {run}ruff format --check .",
        "      - name: Lint",
        f"        run: {run}ruff check .",
        "      - name: Typecheck",
        f"        run: {run}mypy .",
        "      - name: Test",
        f"        run: {run}pytest",
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
    return f"""\
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
      - uses: {CHECKOUT_ACTION}
        with:
          fetch-depth: 0
      - name: Install gitleaks
        run: |
          curl -sSfL -o gitleaks.tar.gz \\
            "https://github.com/gitleaks/gitleaks/releases/download/v{GITLEAKS_VERSION}/gitleaks_{GITLEAKS_VERSION}_linux_x64.tar.gz"
          tar -xzf gitleaks.tar.gz gitleaks
          install -m 0755 gitleaks /usr/local/bin/gitleaks
      - name: Scan history
        run: gitleaks git . --redact --exit-code 2
      - name: Scan working tree
        run: gitleaks dir . --redact --exit-code 2
"""
