"""P0: survey the repository and name every gap.

Pure: every fact was already read from disk by ``gather_facts``. A repository
missing absolutely everything is the normal input here, not an error case.
"""

from __future__ import annotations

from .detect.ci import detect_ci, missing_runners
from .detect.package_manager import detect_package_manager
from .detect.sizes import DEFAULT_FILE_LINE_LIMIT, summarize_sizes
from .detect.tooling import detect_framework, detect_tooling, requires_python
from .facts import RepoFacts
from .models import CiCoverage, Diagnosis, Gap, SizeDistribution, ToolingPresence

# Enough to recognise the workflow they live in; the rest is a count, not a wall of refs.
_ACTIONS_NAMED = 3


def _tooling_gaps(tooling: ToolingPresence) -> list[Gap]:
    gaps: list[Gap] = []
    if not tooling.ruff:
        gaps.append(
            Gap(
                id="ruff",
                title="Ruff is not configured",
                detail="Nothing enforces anything yet. This is the first thing bootstrap installs — "
                "one tool covers linting, import order and formatting.",
                phase="bootstrap",
            )
        )
    if not tooling.formatter:
        gaps.append(
            Gap(
                id="formatter",
                title="No formatter",
                detail="Formatting must land before linting starts, or the first drain PR is a diff "
                "nobody can read. `ruff format` comes free with the Ruff config.",
                phase="bootstrap",
            )
        )
    if not tooling.mypy:
        gaps.append(
            Gap(
                id="mypy",
                title="No type checking",
                detail="Type hints are the cheapest rule set there is. mypy errors are "
                "grandfathered per file per rule, one `mypy:<code>` cell at a time, exactly as "
                "Ruff findings are.",
                phase="bootstrap",
            )
        )
    elif not tooling.mypy_strict:
        gaps.append(
            Gap(
                id="mypy-strict",
                title="mypy `strict` is off",
                detail="Everything else in the type tier is moot until this is on. Enable it and "
                "let the per-cell ratchet hold the line while the backlog drains.",
                phase="tighten",
            )
        )
    if not tooling.pytest:
        gaps.append(
            Gap(
                id="pytest",
                title="No test runner",
                detail="Draining violations finds bugs. Without a runner there is nowhere to pin them.",
                phase="bootstrap",
            )
        )
    if not tooling.vulture:
        gaps.append(
            Gap(
                id="vulture",
                title="No dead-code detection",
                detail="vulture reports unused functions, classes and variables. Report-only at "
                "first; a counter later.",
                phase="tighten",
            )
        )
    if not tooling.secret_scanning:
        gaps.append(
            Gap(
                id="secret-scan",
                title="Nothing would notice a committed credential",
                detail="The one check with no baseline: a leaked key is already public, so it gates "
                "from the first run. GitHub's own push protection is a repository setting and "
                "cannot be seen from here, so ignore this if that is on.",
                phase="bootstrap",
            )
        )
    if not tooling.agent_instructions:
        gaps.append(
            Gap(
                id="agent-instructions",
                title="No CLAUDE.md / AGENTS.md",
                detail="Draining is done by agents. Rules that live only in your head produce a "
                "different fix every session.",
                phase="drain",
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


def diagnose(facts: RepoFacts) -> Diagnosis:
    workflow_text = "\n".join(workflow.content for workflow in facts.workflows)
    tooling = detect_tooling(facts.root_entries, facts.pyproject, facts.extra_config_text, workflow_text)
    ci = detect_ci(facts.workflows)
    sizes = summarize_sizes(facts.source_files)
    gaps = [*_tooling_gaps(tooling), *_ci_gaps(ci), *_size_gaps(sizes)]
    return Diagnosis(
        package_manager=detect_package_manager(facts.root_entries, facts.pyproject),
        requires_python=requires_python(facts.pyproject),
        framework=detect_framework(facts.pyproject),
        tooling=tooling,
        ci=ci,
        sizes=sizes,
        gaps=tuple(gaps),
    )
