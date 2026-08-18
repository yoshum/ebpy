"""The ledger: ``.ebpy/state.json``.

Counts per rule, plain counters, the work log, and the diagnosis provenance.
Everything QUALITY.md shows is rendered from here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .models import (
    LOG_KINDS,
    PHASE_ORDER,
    Counter,
    LogEntry,
    LogKind,
    Phase,
    Regression,
    RuleBaseline,
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

# Kept bounded: this file is read whole on every command, and a log is the thing that grows.
MAX_LOG_ENTRIES = 200


@dataclass(frozen=True)
class Ledger:
    """Whether the state file exists, and the state it holds when readable."""

    exists: bool
    state: State | None


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


def _is_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _is_optional_string(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _has_valid_state_shape(raw: dict[str, Any]) -> bool:
    rules = raw.get("rules")
    counters = raw.get("counters")
    log = raw.get("log", [])
    phase = raw.get("phase", "diagnose")
    frozen_at = raw.get("frozenAt")
    if (
        raw.get("version") != 1
        or raw.get("tool", "ebpy") != "ebpy"
        or phase not in PHASE_ORDER
        or ("updatedAt" in raw and not isinstance(raw["updatedAt"], str))
        or (frozen_at is not None and (not isinstance(frozen_at, str) or not frozen_at))
        or not _is_optional_string(raw.get("diagnosedAt"))
        or not _is_optional_string(raw.get("diagnosedCommit"))
        or (raw.get("diagnosis") is not None and not isinstance(raw.get("diagnosis"), dict))
        or not isinstance(rules, dict)
        or not isinstance(counters, dict)
        or not isinstance(log, list)
    ):
        return False
    if any(
        not isinstance(name, str)
        or not name
        or not isinstance(rule, dict)
        or not _is_count(rule.get("baseline"))
        or not _is_count(rule.get("current"))
        or rule.get("status") not in ("off", "draining", "enforced")
        for name, rule in rules.items()
    ):
        return False
    if any(
        not isinstance(name, str)
        or not name
        or not isinstance(counter, dict)
        or not _is_count(counter.get("baseline"))
        or not _is_count(counter.get("current"))
        for name, counter in counters.items()
    ):
        return False
    return all(
        isinstance(entry, dict)
        and isinstance(entry.get("at"), str)
        and _is_optional_string(entry.get("commit"))
        and entry.get("kind") in LOG_KINDS
        and isinstance(entry.get("text"), str)
        and _is_optional_string(entry.get("rule"))
        for entry in log
    )


def state_from_dict(raw: dict[str, Any]) -> State | None:
    if not _has_valid_state_shape(raw):
        return None
    rules_raw = raw["rules"]
    counters_raw = raw["counters"]
    log_raw = raw.get("log", [])
    diagnosis_raw = raw.get("diagnosis")
    try:
        return State(
            version=1,
            tool=str(raw.get("tool", "ebpy")),
            phase=raw.get("phase", "diagnose"),
            updated_at=str(raw.get("updatedAt", "")),
            frozen_at=raw.get("frozenAt"),
            diagnosed_at=raw.get("diagnosedAt"),
            diagnosed_commit=raw.get("diagnosedCommit"),
            diagnosis=diagnosis_from_dict(diagnosis_raw) if isinstance(diagnosis_raw, dict) else None,
            rules={
                name: RuleBaseline(
                    baseline=int(rule.get("baseline") or 0),
                    current=int(rule.get("current") or 0),
                    status=rule.get("status", "draining"),
                )
                for name, rule in rules_raw.items()
            },
            counters={
                name: Counter(
                    baseline=int(counter.get("baseline") or 0),
                    current=int(counter.get("current") or 0),
                )
                for name, counter in counters_raw.items()
            },
            log=[_entry_from_dict(entry) for entry in log_raw],
        )
    except (AttributeError, OverflowError, TypeError, ValueError):
        return None


def state_to_dict(state: State) -> dict[str, Any]:
    return {
        "version": state.version,
        "tool": state.tool,
        "phase": state.phase,
        "updatedAt": state.updated_at,
        "frozenAt": state.frozen_at,
        "diagnosedAt": state.diagnosed_at,
        "diagnosedCommit": state.diagnosed_commit,
        "diagnosis": state.diagnosis.to_dict() if state.diagnosis else None,
        "rules": {
            name: {"baseline": rule.baseline, "current": rule.current, "status": rule.status}
            for name, rule in state.rules.items()
        },
        "counters": {
            name: {"baseline": counter.baseline, "current": counter.current}
            for name, counter in state.counters.items()
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
    return Ledger(exists=True, state=state)


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


def apply_rule_counts(state: State, counts: dict[str, int], mode: BaselineMode) -> State:
    names = set(state.rules) | set(counts)
    rules: dict[str, RuleBaseline] = {}
    for name in sorted(names):
        current = counts.get(name, 0)
        existing = state.rules.get(name)
        rules[name] = RuleBaseline(
            baseline=next_baseline(existing.baseline if existing else None, current, mode),
            current=current,
            status="enforced" if current == 0 else (existing.status if existing else "draining"),
        )
    state.rules = rules
    return state


def set_counter(state: State, name: str, current: int, mode: BaselineMode) -> State:
    existing = state.counters.get(name)
    state.counters = {
        **state.counters,
        name: Counter(
            baseline=next_baseline(existing.baseline if existing else None, current, mode),
            current=current,
        ),
    }
    return state


def find_regressions(state: State) -> list[Regression]:
    """The gate. Anything whose count rose above its ceiling, rule and plain counter alike."""
    entries = [
        *((name, rule.baseline, rule.current) for name, rule in state.rules.items()),
        *((name, counter.baseline, counter.current) for name, counter in state.counters.items()),
    ]
    return [
        Regression(name=name, baseline=baseline, current=current)
        for name, baseline, current in entries
        if current > baseline
    ]


def improvements(state: State) -> list[Regression]:
    return [
        Regression(name=name, baseline=rule.baseline, current=rule.current)
        for name, rule in state.rules.items()
        if rule.current < rule.baseline
    ]


def total_violations(state: State) -> int:
    return sum(rule.current for rule in state.rules.values())
