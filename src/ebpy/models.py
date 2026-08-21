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

Phase = Literal["diagnose", "bootstrap", "freeze", "drain", "tighten", "split", "review"]

PHASE_ORDER: tuple[Phase, ...] = ("diagnose", "bootstrap", "freeze", "drain", "tighten", "split", "review")

RuleStatus = Literal["off", "draining", "enforced"]

LogKind = Literal["drained", "deferred", "issue", "note"]

LOG_KINDS: tuple[LogKind, ...] = ("drained", "deferred", "issue", "note")

CellCounts = dict[str, dict[RuleId, int]]
CellCountsView: TypeAlias = Mapping[str, Mapping[RuleId, int]]


@dataclass(frozen=True)
class SourceFile:
    path: str
    lines: int


@dataclass(frozen=True)
class UnattributedFinding:
    file: str
    line: int
    message: str


@dataclass(frozen=True)
class AnalysisMeasurement:
    """Today's per-file per-rule findings from one analyzer, in the shape the ratchet compares."""

    cells: CellCountsView
    # Syntax errors cannot be grandfathered: a file that does not parse is invisible
    # to every rule, so recording a rule count for it would be a lie.
    unattributed: tuple[UnattributedFinding, ...] = ()

    def __post_init__(self) -> None:
        frozen_cells = {file: MappingProxyType(dict(rules)) for file, rules in self.cells.items()}
        object.__setattr__(self, "cells", MappingProxyType(frozen_cells))

    @property
    def files_with_findings(self) -> int:
        """Files carrying at least one finding, attributed or not. Clean output reports zero."""
        return len(set(self.cells) | {finding.file for finding in self.unattributed})


@dataclass(frozen=True)
class WorkflowFile:
    path: str
    content: str


@dataclass(frozen=True)
class ToolingPresence:
    ruff: bool
    formatter: bool
    mypy: bool
    mypy_strict: bool
    pytest: bool
    vulture: bool
    pre_commit: bool
    # Anything that would notice a committed credential. Not drainable — see secret_scan.py.
    secret_scanning: bool
    agent_instructions: tuple[str, ...]


@dataclass(frozen=True)
class CiCoverage:
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
    total: int
    over_file_limit: int
    largest: tuple[SourceFile, ...]


@dataclass(frozen=True)
class Gap:
    id: str
    title: str
    detail: str
    phase: Phase


@dataclass(frozen=True)
class Diagnosis:
    package_manager: PackageManager
    requires_python: str | None
    framework: Framework
    tooling: ToolingPresence
    ci: CiCoverage
    sizes: SizeDistribution
    gaps: tuple[Gap, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "packageManager": self.package_manager,
            "requiresPython": self.requires_python,
            "framework": self.framework,
            "tooling": {
                "ruff": self.tooling.ruff,
                "formatter": self.tooling.formatter,
                "mypy": self.tooling.mypy,
                "mypyStrict": self.tooling.mypy_strict,
                "pytest": self.tooling.pytest,
                "vulture": self.tooling.vulture,
                "preCommit": self.tooling.pre_commit,
                "secretScanning": self.tooling.secret_scanning,
                "agentInstructions": list(self.tooling.agent_instructions),
            },
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
    tooling = raw.get("tooling") or {}
    ci = raw.get("ci") or {}
    sizes = raw.get("sizes") or {}
    return Diagnosis(
        package_manager=raw.get("packageManager", "pip"),
        requires_python=raw.get("requiresPython"),
        framework=raw.get("framework", "none"),
        tooling=ToolingPresence(
            ruff=bool(tooling.get("ruff")),
            formatter=bool(tooling.get("formatter")),
            mypy=bool(tooling.get("mypy")),
            mypy_strict=bool(tooling.get("mypyStrict")),
            pytest=bool(tooling.get("pytest")),
            vulture=bool(tooling.get("vulture")),
            pre_commit=bool(tooling.get("preCommit")),
            secret_scanning=bool(tooling.get("secretScanning")),
            agent_instructions=tuple(tooling.get("agentInstructions") or ()),
        ),
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
    baseline: int
    current: int
    status: RuleStatus


STATE_VERSION = 2


@dataclass(frozen=True)
class LogEntry:
    at: str
    # HEAD when this was written. Without it a note cannot be aged.
    commit: str | None
    kind: LogKind
    text: str
    rule: str | None = None


@dataclass
class State:
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
    name: str
    baseline: int
    current: int
