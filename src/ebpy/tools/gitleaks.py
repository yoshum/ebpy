"""Secret-scanning detector and provisioner: configuration detection, diagnosis, and provisioning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ebpy.decide.provisioner import CreateFile
from ebpy.generate.workflows import CHECKOUT_ACTION
from ebpy.models import Gap, ToolSetup

if TYPE_CHECKING:
    from ebpy.decide.provisioner import FileAction, ProvisionContext
    from ebpy.models import Language
    from ebpy.repo.facts import RepoFacts

# The MIT CLI rather than gitleaks-action, which needs a licence key under a GitHub
# Organization. Verified against a digest below, because a release asset can be replaced
# in place under the same tag — and it is this binary that decides whether a leaked
# credential gets reported.
GITLEAKS_VERSION = "8.30.1"
GITLEAKS_SHA256 = "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"


def secret_scan_workflow() -> str:
    """Scan committed history and the working tree for leaked secrets.

    fetch-depth: 0 because a shallow clone misses the commit that leaked, and
    --redact so the secret does not land in a public log.
    """
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


def secret_scan_configured(root_entries: tuple[str, ...], workflow_text: str, pre_commit_text: str) -> bool:
    """Return True when a known secret-scanning tool is referenced in workflows or pre-commit config."""
    return (
        bool(re.search(r"gitleaks|detect-secrets|trufflehog", workflow_text + pre_commit_text, re.IGNORECASE))
        or ".gitleaks.toml" in root_entries
    )


@dataclass(frozen=True)
class GitleaksDetector:
    """Detects whether secret scanning is configured and reports any gaps."""

    @property
    def name(self) -> str:
        """Unique short identifier for secret scanning."""
        return "secret-scan"

    @property
    def languages(self) -> frozenset[Language]:
        """Empty: secret scanning reads workflows and pre-commit config, not source in any language."""
        return frozenset()

    def detect(self, facts: RepoFacts) -> ToolSetup:
        """Return configured=True when a known secret-scanning tool is referenced."""
        workflow_text = "\n".join(workflow.content for workflow in facts.workflows)
        pre_commit_text = facts.extra_config_text.get(".pre-commit-config.yaml") or ""
        return ToolSetup(
            configured=secret_scan_configured(facts.root_entries, workflow_text, pre_commit_text)
        )

    def gaps(self, setup: ToolSetup) -> list[Gap]:
        """Return a bootstrap gap when no secret scanning is configured, empty otherwise."""
        if setup.configured:
            return []
        return [
            Gap(
                id="secret-scan",
                title="Nothing would notice a committed credential",
                detail="The one check with no baseline: a leaked key is already public, so it gates "
                "from the first run. GitHub's own push protection is a repository setting and "
                "cannot be seen from here, so ignore this if that is on.",
                phase="bootstrap",
            )
        ]

    def render_row(self, setup: ToolSetup) -> str:
        """Render a one-line secret scanning row for the diagnosis table."""
        return f"  secret scanning   {'yes' if setup.configured else 'no'}"


@dataclass(frozen=True)
class GitleaksProvisioner:
    """Provisioner for secret scanning: owns the standalone secret-scan.yml workflow.

    gitleaks is not a Python package, so it installs nothing. Its whole contribution is a
    self-contained workflow file it creates outright — the one check with no baseline.
    """

    @property
    def name(self) -> str:
        """Unique short identifier for secret scanning."""
        return "secret-scan"

    def plan_packages(self, setup: ToolSetup) -> tuple[str, ...]:
        """Return empty tuple: gitleaks is not a Python package dependency."""
        return ()

    def plan_file_actions(self, setup: ToolSetup, ctx: ProvisionContext) -> list[FileAction]:
        """Create secret-scan.yml unconditionally; the applier skips it if the file already exists."""
        return [
            CreateFile(
                path=".github/workflows/secret-scan.yml",
                content=secret_scan_workflow(),
                reason="gitleaks over history and working tree — the one check with no baseline",
            )
        ]
