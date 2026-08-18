"""QUALITY.md, rendered from the ledger.

Pure: same state and same notes render the same file, so the diff on every run
is exactly the numbers that moved.
"""

from __future__ import annotations

from ..freshness import Freshness
from ..models import PHASE_ORDER, Gap, LogEntry, RuleBaseline, State
from ..state import find_regressions, improvements, log_of_kind, total_violations
from .worklist import build_worklist, render_worklist

QUALITY_FILE = "QUALITY.md"

# Text between these markers is the owner's, and every render puts it back untouched.
NOTES_START = "<!-- ebpy:notes:start -->"
NOTES_END = "<!-- ebpy:notes:end -->"

_STATUS_LABEL = {"off": "off", "draining": "draining", "enforced": "clean"}

_LOG_ENTRIES_SHOWN = 20


def _delta(rule: RuleBaseline) -> str:
    change = rule.current - rule.baseline
    return f"+{change}" if change > 0 else str(change)


def _rules_table(state: State) -> list[str]:
    rows = sorted(
        ((name, rule) for name, rule in state.rules.items() if rule.baseline > 0 or rule.current > 0),
        key=lambda item: (-item[1].current, item[0]),
    )
    if not rows:
        # "Nothing measured yet" and "measured, and there was nothing" are different
        # facts, and telling a repository that has already frozen to go and freeze
        # reads as the tool having lost track of where it is.
        return [
            "Nothing to grandfather — the freeze found no violations."
            if state.frozen_at
            else "No rule violations recorded yet. Run `ebpy freeze`.",
            "",
        ]
    return [
        "| Rule | Ceiling | Now | Change | Status |",
        "| --- | ---: | ---: | ---: | --- |",
        *(
            f"| `{name}` | {rule.baseline} | {rule.current} | {_delta(rule)} | "
            f"{_STATUS_LABEL.get(rule.status, rule.status)} |"
            for name, rule in rows
        ),
        "",
    ]


def _counters_table(state: State) -> list[str]:
    if not state.counters:
        return []
    return [
        "## Other counters",
        "",
        "| Counter | Ceiling | Now |",
        "| --- | ---: | ---: |",
        *(
            f"| {name} | {counter.baseline} | {counter.current} |"
            for name, counter in sorted(state.counters.items())
        ),
        "",
    ]


def _gaps_checklist(gaps: tuple[Gap, ...]) -> list[str]:
    if not gaps:
        return ["Nothing outstanding.", ""]
    lines: list[str] = []
    for phase in PHASE_ORDER:
        phase_gaps = [gap for gap in gaps if gap.phase == phase]
        if not phase_gaps:
            continue
        lines.extend([f"### {phase}", ""])
        lines.extend(f"- [ ] **{gap.title}** — {gap.detail}" for gap in phase_gaps)
        lines.append("")
    return lines


def _short_commit(commit: str | None) -> str:
    return commit[:8] if commit else "unknown"


def _provenance(entry: LogEntry) -> str:
    return f"_({entry.at[:10]}, {_short_commit(entry.commit)})_"


def _carried_over(state: State) -> list[str]:
    """Deferred work is the section that decays. Each entry carries the commit it was
    written at, so a reader can see whether the observation predates half the repo."""
    deferred = log_of_kind(state, "deferred")
    if not deferred:
        return []
    return [
        "## Carried over",
        "",
        "Refactors left undone, with the commit each was seen at. Re-check before acting on an old one.",
        "",
        *(
            f"- [ ] {f'`{entry.rule}` — ' if entry.rule else ''}{entry.text}  {_provenance(entry)}"
            for entry in deferred
        ),
        "",
    ]


def _work_log(state: State) -> list[str]:
    entries = list(reversed(state.log[-_LOG_ENTRIES_SHOWN:]))
    if not entries:
        return []
    return [
        "## Work log",
        "",
        "| Date | Commit | Kind | Rule | What |",
        "| --- | --- | --- | --- | --- |",
        *(
            f"| {entry.at[:10]} | {_short_commit(entry.commit)} | {entry.kind} | "
            f"{entry.rule or ''} | {entry.text} |"
            for entry in entries
        ),
        "",
    ]


def _freshness_banner(freshness: Freshness) -> list[str]:
    if not freshness.stale:
        return []
    return [
        f"> **The diagnosis below is stale** — {freshness.reason}.",
        "> Numbers and file names may describe code that has since moved.",
        "",
    ]


def _headline(state: State) -> list[str]:
    regressions = find_regressions(state)
    gained = improvements(state)
    verdict = (
        f"{len(regressions)} counter(s) above the ceiling — this is what `ebpy check` fails on."
        if regressions
        else "Everything is at or below its ceiling."
    )
    return [
        f"- Phase: **{state.phase}**",
        f"- Frozen: {state.frozen_at or 'not yet — run `ebpy freeze`'}",
        f"- Open violations: **{total_violations(state)}**",
        f"- Rules improved since the ceiling: **{len(gained)}**",
        f"- {verdict}",
        "",
    ]


def extract_notes(existing: str | None) -> str:
    if not existing:
        return ""
    start = existing.find(NOTES_START)
    end = existing.find(NOTES_END)
    if start == -1 or end == -1 or end < start:
        return ""
    return existing[start + len(NOTES_START) : end].strip()


def render_quality(state: State, notes: str, freshness: Freshness) -> str:
    lines = [
        "# Quality",
        "",
        "Maintained by [ebpy](https://github.com/yoshum/ebpy). Numbers are rendered from",
        "`.ebpy/state.json`; edits outside the notes block are overwritten on the next run.",
        "",
        *_freshness_banner(freshness),
        *_headline(state),
        "## Worklist",
        "",
        "Top to bottom. An unattended run works this list and nothing else.",
        "",
        *render_worklist(build_worklist(state)),
        "",
        *_carried_over(state),
        "## Ratchet",
        "",
        "Ceiling is the count at the last freeze. It may fall and must never rise.",
        "",
        *_rules_table(state),
        *_counters_table(state),
        "## Outstanding",
        "",
        *_gaps_checklist(state.diagnosis.gaps if state.diagnosis else ()),
        *_work_log(state),
        "## Notes",
        "",
        NOTES_START,
        notes if notes else "_Anything written between these markers survives a re-render._",
        NOTES_END,
        "",
    ]
    return "\n".join(lines)
