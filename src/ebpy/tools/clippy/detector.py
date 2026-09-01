"""clippy configuration detection: the setup value, its detection, and the gaps it reports.

`configured` claims one thing only — that this repository configured clippy. `Cargo.toml`
existing claims something else, that the repository contains Rust, and folding the second
into the first would put language detection back inside a detector. The "Rust is here but
clippy holds no ceiling" proposal comes from language detection and the frozen roster.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ebpy.models import Gap, ToolSetup
from ebpy.repo.facts import InvalidToml

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import PurePosixPath

    from ebpy.models import Language
    from ebpy.repo.facts import RepoFacts

# `+toolchain` between the two words is a spelling rustup supports and CI files use;
# `cargo\s+clippy` alone silently misses `cargo +nightly clippy`. Case-sensitive, because
# cargo's subcommands are lowercase. Comment lines are deliberately not excluded: `detect_ci`
# already matches raw YAML with regexes, and parsing here would make two rules disagree
# about one repository.
_CLIPPY_INVOCATION = re.compile(r"\bcargo(?:\s+\+\S+)?\s+clippy\b")


@dataclass(frozen=True)
class ClippySetup(ToolSetup):
    """Detection result for clippy, extending ToolSetup with the manifests it could not read."""

    invalid_manifests: tuple[InvalidToml, ...]


def _lint_table_present(manifest: dict[str, Any]) -> bool:
    workspace = manifest.get("workspace")
    # A value that parsed as valid TOML is not thereby a table: `workspace = "x"` parses fine
    # and would raise AttributeError on `.get("lints")` without this guard.
    workspace_lints = workspace.get("lints") if isinstance(workspace, dict) else None
    for table in (manifest.get("lints"), workspace_lints):
        if isinstance(table, dict) and isinstance(table.get("clippy"), dict):
            return True
    return False


def _config_covers_a_manifest(
    config_paths: tuple[PurePosixPath, ...], manifests: Mapping[PurePosixPath, object]
) -> bool:
    """Whether a clippy config sits above some Cargo manifest.

    An approximation of Clippy's own search, which walks up from CLIPPY_CONF_DIR, the manifest
    directory, and the cwd. ebpy does not reproduce the environment variables, so it stops at
    "in an ancestor of a manifest" — and says so rather than claiming to know what Clippy will
    read. The naive "any clippy.toml anywhere" would let one file under tests/fixtures/ mark a
    whole repository configured.
    """
    directories = {manifest.parent for manifest in manifests}
    return any(
        config.parent == directory or config.parent in directory.parents
        for config in config_paths
        for directory in directories
    )


@dataclass(frozen=True)
class ClippyDetector:
    """Detects whether clippy is configured and reports the manifests it could not read."""

    @property
    def name(self) -> str:
        """Unique short identifier for clippy."""
        return "clippy"

    @property
    def languages(self) -> frozenset[Language]:
        """Clippy is a Rust tool."""
        return frozenset({"rust"})

    @property
    def requires_repository_setup(self) -> bool:
        """False: clippy has no adoption step to wait for, so the language's presence is enough."""
        return False

    def detect(self, facts: RepoFacts) -> ClippySetup:
        """Return clippy's configuration state, keeping unreadable manifests apart from absent ones."""
        invalid = tuple(
            manifest
            for _, manifest in sorted(facts.cargo_manifests.items())
            if isinstance(manifest, InvalidToml)
        )
        text = "\n".join(
            [
                *(workflow.content for workflow in facts.workflows),
                facts.extra_config_text.get(".pre-commit-config.yaml") or "",
            ]
        )
        configured = (
            _config_covers_a_manifest(facts.clippy_config_paths, facts.cargo_manifests)
            or any(
                _lint_table_present(manifest)
                for manifest in facts.cargo_manifests.values()
                if isinstance(manifest, dict)
            )
            or _CLIPPY_INVOCATION.search(text) is not None
        )
        return ClippySetup(configured=configured, invalid_manifests=invalid)

    def gaps(self, setup: ClippySetup) -> list[Gap]:
        """Name each manifest that could not be read. Being unconfigured is not a gap.

        clippy runs with no repository configuration (so there is nothing to install) and has
        no provisioner, so a "not configured" gap would have no way to be closed — and it
        would say the same thing as the unratcheted gap already does. One gap per manifest,
        not one aggregate: after fixing two of three, a reader has to see which is left.
        """
        return [
            Gap(
                id=f"clippy-manifest:{manifest.path}",
                title=f"{manifest.path} could not be read as TOML",
                detail=f"{manifest.detail} — clippy's configuration in this file was not counted.",
                phase="tighten",
            )
            for manifest in setup.invalid_manifests
        ]

    def render_row(self, setup: ClippySetup) -> str:
        """Render a one-line clippy row for the diagnosis table."""
        # The parenthetical is here because clippy is the one tool of the seven that still
        # works unconfigured, which changes what "no" means on this row alone.
        state = "configured" if setup.configured else "not configured (runs with defaults)"
        return f"  clippy            {state}"
