"""Secret-scanning detector: configuration detection and diagnosis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import Gap, ToolSetup

if TYPE_CHECKING:
    from ..repo.facts import RepoFacts


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
