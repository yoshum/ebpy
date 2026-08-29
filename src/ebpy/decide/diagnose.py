"""P0: survey the repository and name every gap.

Pure: every fact was already read from disk by ``gather_facts``. A repository
missing absolutely everything is the normal input here, not an error case.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ebpy.models import CiCoverage, Diagnosis, Gap, SizeDistribution, ToolSetup
from ebpy.repo.detect.ci import detect_ci, missing_runners
from ebpy.repo.detect.package_manager import detect_package_manager
from ebpy.repo.detect.sizes import DEFAULT_FILE_LINE_LIMIT, summarize_sizes
from ebpy.repo.detect.tooling import (
    detect_agent_instructions,
    detect_framework,
    pre_commit_configured,
    requires_python,
)
from ebpy.tools import ANALYZERS_BY_NAME, DETECTORS

if TYPE_CHECKING:
    from ebpy.models import Language
    from ebpy.repo.facts import RepoFacts

# Enough to recognise the workflow they live in; the rest is a count, not a wall of refs.
_ACTIONS_NAMED = 3


def _agent_instruction_gaps(agent_instructions: tuple[str, ...]) -> list[Gap]:
    if agent_instructions:
        return []
    return [
        Gap(
            id="agent-instructions",
            title="No CLAUDE.md / AGENTS.md",
            detail="Draining is done by agents. Rules that live only in your head produce a "
            "different fix every session.",
            phase="drain",
        )
    ]


def _unratcheted_gaps(tool_setups: dict[str, ToolSetup], frozen_analyzers: tuple[str, ...]) -> list[Gap]:
    """Report a gap per analyzer this repository configures but the frozen contract omits.

    Only the registered analyzers (ruff, mypy) can be ratcheted, so only they can be
    "configured but not ratcheted"; the other tools are report-only. These derive from
    detected configuration, which is always present here — there is no absence to confuse
    with zero.
    """
    roster = set(frozen_analyzers)
    gaps: list[Gap] = []
    for name in ANALYZERS_BY_NAME:
        setup = tool_setups.get(name)
        if setup is not None and setup.configured and name not in roster:
            gaps.append(
                Gap(
                    id=f"unratcheted:{name}",
                    title=f"{name} is configured but not ratcheted",
                    detail=f"{name} runs in this repository but is not in the frozen contract, so its "
                    f"findings hold no ceiling. `ebpy freeze --analyzer {name}` pins them.",
                    phase="tighten",
                )
            )
    return gaps


def _ci_gaps(ci: CiCoverage) -> list[Gap]:
    if not ci.present:
        return [
            Gap(
                id="ci",
                title="No CI workflows",
                detail="The baseline is only a ratchet if something rejects a regression. Without CI "
                "it is a note.",
                phase="review",
            )
        ]
    gaps: list[Gap] = []
    runners = missing_runners(ci)
    if runners:
        gaps.append(
            Gap(
                id="ci-runners",
                title=f"CI does not run on {', '.join(runners)}",
                detail="Path handling and file watching break per platform, and only per platform.",
                phase="review",
            )
        )
    if not ci.runs_lint:
        gaps.append(
            Gap(
                id="ci-lint",
                title="CI does not run lint",
                detail="The rules are configured but nothing runs them on a pull request.",
                phase="review",
            )
        )
    if ci.unpinned_actions:
        shown = ", ".join(ci.unpinned_actions[:_ACTIONS_NAMED])
        more = len(ci.unpinned_actions) - _ACTIONS_NAMED
        gaps.append(
            Gap(
                id="ci-action-pins",
                title=f"{len(ci.unpinned_actions)} action(s) not pinned to a commit",
                detail=f"{shown}{f' + {more} more' if more > 0 else ''}. A tag is not a pin: whoever "
                "owns the action can move it onto new code, and CI would run that without a diff — "
                "with whatever token the job holds. Pin each to a full commit SHA and let dependabot "
                "bump them.",
                phase="review",
            )
        )
    if not ci.runs_ebpy_check:
        gaps.append(
            Gap(
                id="ci-gate",
                title="CI does not run `ebpy check`",
                detail="A baseline is only a ratchet if something rejects a regression. Thorough CI "
                "that never runs the gate enforces nothing, and looks identical from the outside.",
                phase="review",
            )
        )
    return gaps


def _size_gaps(sizes: SizeDistribution) -> list[Gap]:
    if sizes.over_file_limit == 0:
        return []
    return [
        Gap(
            id="file-size",
            title=f"{sizes.over_file_limit} files over {DEFAULT_FILE_LINE_LIMIT} lines",
            detail="These are the split-and-DRY backlog. Knowing the count now makes the limit a choice.",
            phase="split",
        )
    ]


def diagnose(
    facts: RepoFacts, frozen_analyzers: tuple[str, ...], languages: frozenset[Language]
) -> Diagnosis:
    """Survey the repository, naming every gap.

    `frozen_analyzers` is the roster the ledger already holds — empty for a repository that
    has never frozen. It is what tells a configured analyzer apart from a ratcheted one, so
    the "configured but not ratcheted" gap can be raised.

    `languages` narrows the detectors that run: a Cargo-less repository would otherwise carry
    a permanent clippy row and a gap with no way to close it. A detector with an empty
    `languages` (secret scanning) is repository-wide and always runs — the `not d.languages`
    check below, not a membership test, is what lets it through.
    """
    detectors = tuple(d for d in DETECTORS if not d.languages or d.languages & languages)
    tool_setups = {detector.name: detector.detect(facts) for detector in detectors}
    agent_instructions = detect_agent_instructions(facts.root_entries)
    ci = detect_ci(facts.workflows)
    sizes = summarize_sizes(facts.source_files)
    gaps = [
        *(gap for detector in detectors for gap in detector.gaps(tool_setups[detector.name])),
        *_agent_instruction_gaps(agent_instructions),
        *_ci_gaps(ci),
        *_size_gaps(sizes),
        *_unratcheted_gaps(tool_setups, frozen_analyzers),
    ]
    return Diagnosis(
        package_manager=detect_package_manager(facts.root_entries, facts.pyproject),
        requires_python=requires_python(facts.pyproject),
        framework=detect_framework(facts.pyproject),
        tool_setups=tool_setups,
        pre_commit=pre_commit_configured(facts.root_entries),
        agent_instructions=agent_instructions,
        ci=ci,
        sizes=sizes,
        gaps=tuple(gaps),
    )
