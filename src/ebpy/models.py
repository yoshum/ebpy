"""The data every command shares, in one place.

Mirrors ever-better's ``types.ts``: decisions are pure functions over these
values, and the disk access lives in the modules that build them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, TypeAlias

AnalyzerName: TypeAlias = str

RuleId: TypeAlias = str

PackageManager = Literal["uv", "poetry", "pdm", "pipenv", "pip"]

Framework = Literal["django", "fastapi", "flask", "none"]

# Singular deliberately: all three analyzers measure exactly one language today, and widening
# to a tuple later is a change the type checker points at every call site. A member meaning
# "every language" must never be added — `Framework`'s "none" is an absence, but "any" would
# be a universal, and conflating the two is what "absence and zero are different" forbids.
Language = Literal["python", "rust"]

Phase = Literal["diagnose", "bootstrap", "freeze", "drain", "tighten", "split", "review"]

PHASE_ORDER: tuple[Phase, ...] = ("diagnose", "bootstrap", "freeze", "drain", "tighten", "split", "review")

RuleStatus = Literal["off", "draining", "enforced"]

LogKind = Literal["drained", "deferred", "issue", "note"]

LOG_KINDS: tuple[LogKind, ...] = ("drained", "deferred", "issue", "note")

CellCounts = dict[str, dict[RuleId, int]]
CellCountsView: TypeAlias = Mapping[str, Mapping[RuleId, int]]


@dataclass(frozen=True)
class ToolSetup:
    """Baseline detection result shared by every tool.

    Each tool serializes itself: `to_dict`/`from_dict` are the contract the ledger stores.
    Subclasses (e.g. mypy's) add their own fields by overriding both.
    """

    configured: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize this setup to the JSON shape the ledger stores."""
        return {"configured": self.configured}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ToolSetup:
        """Reconstruct a setup from its stored JSON shape."""
        return cls(configured=bool(raw.get("configured")))


@dataclass(frozen=True)
class SourceFile:
    """A source file and its line count, as measured for the size distribution."""

    path: str
    lines: int


@dataclass(frozen=True)
class UnattributedFinding:
    """A finding no cell can hold — typically a syntax error that hides a file from every rule.

    Not only syntax errors: any finding whose reported location cannot be placed in the
    ceiling's coordinate system lands here, such as a clippy diagnostic for a path outside
    the repository. The invariant is the same either way — a location the ratchet cannot
    key on cannot be grandfathered.
    """

    file: str
    line: int
    message: str


@dataclass(frozen=True)
class UnmeasuredScope:
    """One range of a repository an analyzer could not measure, as the runner saw it.

    Two fields because the identity of the range and the identity of its container are
    different questions. `packages` is what the contract compares — a workspace root can stay
    the same while `members` and `exclude` move packages across it. `root` is what a message
    names, because "which workspace lost the ceiling" needs the container.
    """

    root: str
    packages: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisMeasurement:
    """Today's per-file per-rule findings from one analyzer, in the shape the ratchet compares."""

    cells: CellCountsView
    # Syntax errors cannot be grandfathered: a file that does not parse is invisible
    # to every rule, so recording a rule count for it would be a lie.
    unattributed: tuple[UnattributedFinding, ...] = ()
    # Ranges this run did not measure at all. Distinct from an empty cell mapping, which
    # means the analyzer looked and found nothing.
    unmeasured: tuple[UnmeasuredScope, ...] = ()

    def __post_init__(self) -> None:
        """Freeze ``cells`` into nested read-only proxies so the frozen value is deeply immutable."""
        frozen_cells = {file: MappingProxyType(dict(rules)) for file, rules in self.cells.items()}
        object.__setattr__(self, "cells", MappingProxyType(frozen_cells))

    @property
    def files_with_findings(self) -> int:
        """Files carrying at least one finding, attributed or not. Clean output reports zero."""
        return len(set(self.cells) | {finding.file for finding in self.unattributed})


@dataclass(frozen=True)
class WorkflowFile:
    """A CI workflow file: its repository path and full text."""

    path: str
    content: str


@dataclass(frozen=True)
class CiCoverage:
    """What the repository's CI does: its runners, any unpinned actions, and which gate steps it runs."""

    present: bool
    # Runner labels seen across all workflows, e.g. ("ubuntu-latest", "macos-latest").
    runners: tuple[str, ...]
    # `uses:` references still on a tag or branch. Empty means every one is a commit pin
    # — but only when `present`, since a repo with no workflows has none of either.
    unpinned_actions: tuple[str, ...]
    runs_lint: bool
    runs_typecheck: bool
    runs_test: bool
    runs_ebpy_check: bool


@dataclass(frozen=True)
class SizeDistribution:
    """The backlog sized by file: the total, how many exceed the file-line limit, and the largest few."""

    total: int
    over_file_limit: int
    largest: tuple[SourceFile, ...]


@dataclass(frozen=True)
class Gap:
    """One thing a phase must close before it is done, tagged with the phase that owns it."""

    id: str
    title: str
    detail: str
    phase: Phase


@dataclass(frozen=True)
class Diagnosis:
    """The full picture one diagnose produces: package manager, tools, CI, sizes and each phase's gaps."""

    package_manager: PackageManager
    requires_python: str | None
    framework: Framework
    # One setup per tool detector, keyed by detector name. Each value serializes itself,
    # so a tool with extra provenance (mypy's strictness) carries it without this layer knowing.
    tool_setups: Mapping[str, ToolSetup]
    # Signals that are not owned by a tool detector. pre-commit and the agent instruction
    # files are repository conventions rather than analyzers, so they stay here rather than
    # in tool_setups.
    pre_commit: bool
    agent_instructions: tuple[str, ...]
    ci: CiCoverage
    sizes: SizeDistribution
    gaps: tuple[Gap, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the diagnosis to a JSON-ready dict with camelCase keys."""
        return {
            "packageManager": self.package_manager,
            "requiresPython": self.requires_python,
            "framework": self.framework,
            "toolSetups": {name: setup.to_dict() for name, setup in self.tool_setups.items()},
            "preCommit": self.pre_commit,
            "agentInstructions": list(self.agent_instructions),
            "ci": {
                "present": self.ci.present,
                "runners": list(self.ci.runners),
                "unpinnedActions": list(self.ci.unpinned_actions),
                "runsLint": self.ci.runs_lint,
                "runsTypecheck": self.ci.runs_typecheck,
                "runsTest": self.ci.runs_test,
                "runsEbpyCheck": self.ci.runs_ebpy_check,
            },
            "sizes": {
                "total": self.sizes.total,
                "overFileLimit": self.sizes.over_file_limit,
                "largest": [{"path": f.path, "lines": f.lines} for f in self.sizes.largest],
            },
            "gaps": [{"id": g.id, "title": g.title, "detail": g.detail, "phase": g.phase} for g in self.gaps],
        }


def diagnosis_from_dict(raw: dict[str, Any]) -> Diagnosis:
    """Rebuild a Diagnosis from its stored JSON form."""
    # A legacy `tooling` object from before the per-detector shape is ignored: provenance is
    # regenerated on the next `diagnose`, so there is nothing here worth reconstructing it for.
    tool_setups_raw = raw.get("toolSetups") or {}
    ci = raw.get("ci") or {}
    sizes = raw.get("sizes") or {}
    return Diagnosis(
        package_manager=raw.get("packageManager", "pip"),
        requires_python=raw.get("requiresPython"),
        framework=raw.get("framework", "none"),
        # Every setup reads back as a base ToolSetup: any extra provenance a tool wrote (mypy's
        # strictness) is regenerated on the next `diagnose` and never read from disk, so there is
        # nothing here worth reconstructing the subtype for.
        tool_setups={
            name: ToolSetup.from_dict(value if isinstance(value, dict) else {})
            for name, value in tool_setups_raw.items()
        },
        pre_commit=bool(raw.get("preCommit")),
        agent_instructions=tuple(raw.get("agentInstructions") or ()),
        ci=CiCoverage(
            present=bool(ci.get("present")),
            runners=tuple(ci.get("runners") or ()),
            unpinned_actions=tuple(ci.get("unpinnedActions") or ()),
            runs_lint=bool(ci.get("runsLint")),
            runs_typecheck=bool(ci.get("runsTypecheck")),
            runs_test=bool(ci.get("runsTest")),
            runs_ebpy_check=bool(ci.get("runsEbpyCheck")),
        ),
        sizes=SizeDistribution(
            total=int(sizes.get("total") or 0),
            over_file_limit=int(sizes.get("overFileLimit") or 0),
            largest=tuple(
                SourceFile(path=str(f.get("path", "")), lines=int(f.get("lines") or 0))
                for f in sizes.get("largest") or ()
            ),
        ),
        gaps=tuple(
            Gap(
                id=str(g.get("id", "")),
                title=str(g.get("title", "")),
                detail=str(g.get("detail", "")),
                phase=g.get("phase", "review"),
            )
            for g in raw.get("gaps") or ()
        ),
    )


@dataclass(frozen=True)
class RuleBaseline:
    """One rule in the ratchet: the frozen ceiling, today's count, and its off/draining/enforced status."""

    baseline: int
    current: int
    status: RuleStatus


STATE_VERSION = 2


@dataclass(frozen=True)
class LogEntry:
    """One line of the work log: when and where it was written, its kind, and the rule it concerns."""

    at: str
    # HEAD when this was written. Without it a note cannot be aged.
    commit: str | None
    kind: LogKind
    text: str
    rule: str | None = None


@dataclass
class State:
    """The mutable ledger: phase, freeze provenance, diagnosis, per-rule ceilings and the work log."""

    version: int = STATE_VERSION
    tool: str = "ebpy"
    phase: Phase = "diagnose"
    updated_at: str = ""
    frozen_at: str | None = None
    # When and at which commit the diagnosis below was taken.
    diagnosed_at: str | None = None
    diagnosed_commit: str | None = None
    diagnosis: Diagnosis | None = None
    # Cells alone cannot distinguish "the analyzer ran and found no violations" from "the analyzer
    # never ran". For example, a ceiling of zero is only verifiable if we know which analyzers
    # contributed to that measurement.
    frozen_analyzers: tuple[str, ...] = ()
    # The package-level counterpart to frozen_analyzers, and there for the same reason.
    # `write_cells` drops zero-count cells, so a workspace measured and found clean looks
    # exactly like one never measured — and clean is where every repository is headed.
    # Unmeasured packages are remembered rather than measured ones so that deleting a crate
    # does not read as the contract narrowing.
    unmeasured_packages: tuple[str, ...] = ()
    rules: dict[str, RuleBaseline] = field(default_factory=dict)
    log: list[LogEntry] = field(default_factory=list)


@dataclass(frozen=True)
class Suppression:
    """One cell of the ratchet: how many violations of one rule one file may still hold."""

    file: str
    rule: str
    count: int


@dataclass(frozen=True)
class Regression:
    """A rule whose current count rose above its baseline — the one thing the ratchet forbids."""

    name: str
    baseline: int
    current: int
