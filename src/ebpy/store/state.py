"""The ledger: ``.ebpy/state.json``.

Counts per namespaced rule, the roster of analyzers that have contributed to those counts,
the work log, and the diagnosis provenance. Everything QUALITY.md shows is rendered from here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypeGuard

from ..cell_key import analyzer_of, is_analyzer_name, is_rule_id
from ..models import (
    LOG_KINDS,
    PHASE_ORDER,
    LogEntry,
    LogKind,
    Phase,
    Regression,
    RuleBaseline,
    RuleId,
    State,
    diagnosis_from_dict,
)

STATE_DIR = ".ebpy"
STATE_FILE = "state.json"

# `observe` records today's number without touching the ceiling — what `diagnose` and
# `check` do. `freeze` lowers the ceiling to today's number if it improved, and never
# raises it: running `freeze` twice after a bad week must not legalise the damage.
# `rebaseline` is the explicit `--force` escape for when a ceiling genuinely has to
# move up (a rule was reconfigured).
BaselineMode = Literal["observe", "freeze", "rebaseline"]

RULE_STATUSES = ("off", "draining", "enforced")

# Kept bounded: this file is read whole on every command, and a log is the thing that grows.
MAX_LOG_ENTRIES = 200


@dataclass(frozen=True)
class Ledger:
    """Whether the state file exists, and the state it holds when readable.

    `legacy_version` records a schema version this ebpy no longer reads (only 1 so far). It is
    the difference between "an ebpy wrote this in a format we retired" and "these bytes are
    corrupt" — two facts that must never render the same. It is set only when the file parses
    as JSON and names an old version; genuinely unreadable bytes leave it None.
    """

    exists: bool
    state: State | None
    legacy_version: int | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def state_path(cwd: Path) -> Path:
    return cwd / STATE_DIR / STATE_FILE


def empty_state() -> State:
    return State(updated_at=_now())


def _entry_from_dict(raw: dict[str, Any]) -> LogEntry:
    return LogEntry(
        at=str(raw.get("at", "")),
        commit=raw.get("commit"),
        kind=raw.get("kind", "note"),
        text=str(raw.get("text", "")),
        rule=raw.get("rule"),
    )


def _is_optional_string(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _valid_common_fields(raw: dict[str, Any]) -> bool:
    phase = raw.get("phase", "diagnose")
    frozen_at = raw.get("frozenAt")
    return (
        raw.get("tool", "ebpy") == "ebpy"
        and phase in PHASE_ORDER
        and ("updatedAt" not in raw or isinstance(raw["updatedAt"], str))
        and (frozen_at is None or (isinstance(frozen_at, str) and frozen_at != ""))
        and _is_optional_string(raw.get("diagnosedAt"))
        and _is_optional_string(raw.get("diagnosedCommit"))
        and (raw.get("diagnosis") is None or isinstance(raw.get("diagnosis"), dict))
    )


def _valid_log(log: Any) -> bool:
    return isinstance(log, list) and all(
        isinstance(entry, dict)
        and isinstance(entry.get("at"), str)
        and _is_optional_string(entry.get("commit"))
        and entry.get("kind") in LOG_KINDS
        and isinstance(entry.get("text"), str)
        and (entry.get("rule") is None or is_rule_id(entry.get("rule")))
        for entry in log
    )


def _valid_frozen_analyzers(value: Any) -> TypeGuard[list[str]]:
    return (
        isinstance(value, list)
        and all(isinstance(name, str) and is_analyzer_name(name) for name in value)
        and len(set(value)) == len(value)
    )


def _valid_v2_rule(rule: Any) -> bool:
    baseline = rule.get("baseline") if isinstance(rule, dict) else None
    current = rule.get("current") if isinstance(rule, dict) else None
    return (
        isinstance(rule, dict)
        and type(baseline) is int
        and type(current) is int
        and 0 <= current <= baseline
        and rule.get("status") in RULE_STATUSES
    )


def _valid_v2_rules(rules: Any, frozen_analyzers: list[str]) -> bool:
    if not isinstance(rules, dict):
        return False
    roster = set(frozen_analyzers)
    return all(
        is_rule_id(name) and analyzer_of(name) in roster and _valid_v2_rule(rule)
        for name, rule in rules.items()
    )


def _has_valid_v2_shape(raw: dict[str, Any]) -> bool:
    frozen_analyzers = raw.get("frozenAnalyzers")
    if not _valid_frozen_analyzers(frozen_analyzers):
        return False
    return (
        raw.get("version") == 2
        and "counters" not in raw
        and _valid_common_fields(raw)
        and _valid_v2_rules(raw.get("rules"), frozen_analyzers)
        and _valid_log(raw.get("log", []))
    )


def state_from_dict(raw: dict[str, Any]) -> State | None:
    if not _has_valid_v2_shape(raw):
        return None
    try:
        diagnosis_raw = raw.get("diagnosis")
        return State(
            version=2,
            tool=str(raw.get("tool", "ebpy")),
            phase=raw.get("phase", "diagnose"),
            updated_at=str(raw.get("updatedAt", "")),
            frozen_at=raw.get("frozenAt"),
            diagnosed_at=raw.get("diagnosedAt"),
            diagnosed_commit=raw.get("diagnosedCommit"),
            diagnosis=diagnosis_from_dict(diagnosis_raw) if isinstance(diagnosis_raw, dict) else None,
            frozen_analyzers=tuple(raw["frozenAnalyzers"]),
            rules={
                name: RuleBaseline(baseline=rule["baseline"], current=rule["current"], status=rule["status"])
                for name, rule in raw["rules"].items()
            },
            log=[_entry_from_dict(entry) for entry in raw.get("log", [])],
        )
    except (AttributeError, OverflowError, TypeError, ValueError):
        return None


def state_to_dict(state: State) -> dict[str, Any]:
    return {
        "version": 2,
        "tool": state.tool,
        "phase": state.phase,
        "updatedAt": state.updated_at,
        "frozenAt": state.frozen_at,
        "diagnosedAt": state.diagnosed_at,
        "diagnosedCommit": state.diagnosed_commit,
        "diagnosis": state.diagnosis.to_dict() if state.diagnosis else None,
        "frozenAnalyzers": sorted(state.frozen_analyzers),
        "rules": {
            name: {"baseline": rule.baseline, "current": rule.current, "status": rule.status}
            for name, rule in sorted(state.rules.items(), key=lambda item: item[0])
        },
        "log": [
            {
                "at": entry.at,
                "commit": entry.commit,
                "kind": entry.kind,
                **({"rule": entry.rule} if entry.rule is not None else {}),
                "text": entry.text,
            }
            for entry in state.log
        ],
    }


def read_ledger(cwd: Path) -> Ledger:
    path = state_path(cwd)
    if path.parent.is_symlink() or path.is_symlink():
        return Ledger(exists=True, state=None)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Ledger(exists=False, state=None)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return Ledger(exists=True, state=None)
    state = state_from_dict(raw) if isinstance(raw, dict) else None
    return Ledger(exists=True, state=state, legacy_version=_legacy_version(raw))


def _legacy_version(raw: Any) -> int | None:
    """The schema version of a state.json this ebpy can no longer read, or None.

    Only a file that parses as JSON and names an integer version below the current one counts
    as legacy — that is a format we retired, distinct from bytes that never parsed at all.
    """
    if not isinstance(raw, dict):
        return None
    version = raw.get("version")
    if type(version) is int and version < 2:
        return version
    return None


def write_state(cwd: Path, state: State) -> None:
    path = state_path(cwd)
    if path.parent.is_symlink():
        path.parent.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    state.updated_at = _now()
    path.write_text(json.dumps(state_to_dict(state), indent=2) + "\n", encoding="utf-8")


def with_diagnosis(state: State, diagnosis: Any, commit: str | None) -> State:
    state.diagnosis = diagnosis
    state.diagnosed_at = _now()
    state.diagnosed_commit = commit
    return state


def append_log(state: State, kind: LogKind, text: str, commit: str | None, rule: str | None = None) -> State:
    state.log = [*state.log, LogEntry(at=_now(), commit=commit, kind=kind, text=text, rule=rule)]
    state.log = state.log[-MAX_LOG_ENTRIES:]
    return state


def log_of_kind(state: State, kind: LogKind) -> list[LogEntry]:
    return [entry for entry in state.log if entry.kind == kind]


def with_phase(state: State, phase: Phase) -> State:
    state.phase = phase
    return state


def next_baseline(existing: int | None, current: int, mode: BaselineMode) -> int:
    if existing is None or mode == "rebaseline":
        return current
    return min(existing, current) if mode == "freeze" else existing


def copy_state(state: State) -> State:
    """A caller's own State, safe to hand to the helpers below.

    `State` is deliberately the one mutable value in the codebase, so `apply_analyzer_rule_counts`,
    `replace_analyzer_rules` and `with_phase` rewrite the object they are given. A decision function
    that is pure over its arguments has to copy first, and every one of them needs the same copy —
    so it is spelled once, here, rather than open-coded at each call site.
    """
    return deepcopy(state)


def apply_analyzer_rule_counts(
    state: State, analyzer: str, counts: Mapping[RuleId, int], mode: BaselineMode
) -> State:
    """Rewrite one analyzer's namespace in `state.rules`, leaving every other rule untouched.

    A rule in the namespace that this run no longer reports is drained to `current = 0` with
    its baseline held — not run back through `next_baseline`, which would let a `freeze` collapse
    the ceiling to zero from a mere absence rather than an explicit decision to drain it.
    """
    untouched = {name: rule for name, rule in state.rules.items() if analyzer_of(name) != analyzer}
    namespace_existing = {name: rule for name, rule in state.rules.items() if analyzer_of(name) == analyzer}

    updated: dict[str, RuleBaseline] = {}
    for name in sorted(set(namespace_existing) | set(counts)):
        existing = namespace_existing.get(name)
        if name in counts:
            current = counts[name]
            baseline = next_baseline(existing.baseline if existing else None, current, mode)
        else:
            current = 0
            baseline = namespace_existing[name].baseline
        updated[name] = RuleBaseline(
            baseline=baseline,
            current=current,
            status="enforced" if current == 0 else (existing.status if existing else "draining"),
        )

    state.rules = {**untouched, **updated}
    return state


def replace_analyzer_rules(state: State, analyzer: str, counts: Mapping[RuleId, int]) -> State:
    """Drop every rule in `analyzer`'s namespace and install `counts` as a fresh ceiling.

    Used by scoped freeze: unlike `apply_analyzer_rule_counts`, a rule this run does not report
    is simply gone from the namespace rather than drained to zero — there is no previous baseline
    to hold onto, since the whole namespace is being (re)frozen from today's measurement.
    """
    untouched = {name: rule for name, rule in state.rules.items() if analyzer_of(name) != analyzer}
    replaced = {
        name: RuleBaseline(baseline=count, current=count, status="enforced" if count == 0 else "draining")
        for name, count in counts.items()
    }
    state.rules = {**untouched, **replaced}
    return state


def improvements(state: State) -> list[Regression]:
    return [
        Regression(name=name, baseline=rule.baseline, current=rule.current)
        for name, rule in state.rules.items()
        if rule.current < rule.baseline
    ]


def total_violations(state: State) -> int:
    return sum(rule.current for rule in state.rules.values())
