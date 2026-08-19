from __future__ import annotations

from ebpy.drain_order import build_drain_plan
from ebpy.freshness import Freshness
from ebpy.models import CiCoverage, Diagnosis, RuleBaseline, SizeDistribution, Suppression, ToolingPresence
from ebpy.render.next import render_next
from ebpy.render.quality import NOTES_END, NOTES_START, extract_notes, render_quality
from ebpy.render.worklist import build_worklist, render_worklist
from ebpy.state import append_log, empty_state

CURRENT = Freshness(stale=False, reason="current")
STALE = Freshness(stale=True, reason="42 commits since the diagnosis")


def _diagnosis(*, mypy_configured: bool) -> Diagnosis:
    return Diagnosis(
        package_manager="uv",
        requires_python=None,
        framework="none",
        tooling=ToolingPresence(
            ruff=True,
            formatter=False,
            mypy=mypy_configured,
            mypy_strict=False,
            pytest=False,
            vulture=False,
            pre_commit=False,
            secret_scanning=False,
            agent_instructions=(),
        ),
        ci=CiCoverage(
            present=False,
            runners=(),
            unpinned_actions=(),
            runs_lint=False,
            runs_typecheck=False,
            runs_test=False,
            runs_ebpy_check=False,
        ),
        sizes=SizeDistribution(total=0, over_file_limit=0, largest=()),
        gaps=(),
    )


def test_notes_survive_a_re_render() -> None:
    existing = f"# Quality\n\n{NOTES_START}\nwe skip E501 in migrations on purpose\n{NOTES_END}\n"
    notes = extract_notes(existing)
    assert notes == "we skip E501 in migrations on purpose"
    assert notes in render_quality(empty_state(), notes, CURRENT)


def test_a_file_without_markers_yields_no_notes() -> None:
    assert extract_notes("# Quality\n\nnothing here\n") == ""
    assert extract_notes(None) == ""


def test_rendering_is_pure() -> None:
    state = empty_state()
    assert render_quality(state, "", CURRENT) == render_quality(state, "", CURRENT)


def test_a_stale_diagnosis_is_announced_at_the_top() -> None:
    rendered = render_quality(empty_state(), "", STALE)
    assert "The diagnosis below is stale" in rendered
    assert "42 commits" in rendered


def test_the_ratchet_table_shows_the_change_against_the_ceiling() -> None:
    state = empty_state()
    state.rules = {"E501": RuleBaseline(baseline=10, current=4, status="draining")}
    rendered = render_quality(state, "", CURRENT)
    assert "| `E501` | 10 | 4 | -6 | draining |" in rendered


def test_quality_renders_namespaced_rules_and_no_counters_table() -> None:
    state = empty_state()
    state.rules = {"ruff:E501": RuleBaseline(baseline=10, current=4, status="draining")}
    rendered = render_quality(state, "", CURRENT)
    assert "| `ruff:E501` | 10 | 4 | -6 | draining |" in rendered
    assert "## Other counters" not in rendered


def test_quality_names_the_analyzers_whose_ceiling_it_holds() -> None:
    state = empty_state()
    state.frozen_analyzers = ("mypy", "ruff")
    assert "- Analyzers: **mypy, ruff**" in render_quality(state, "", CURRENT)


def test_quality_says_none_when_no_analyzer_ceiling_is_held() -> None:
    assert "- Analyzers: **none**" in render_quality(empty_state(), "", CURRENT)


def test_quality_flags_a_configured_analyzer_the_contract_does_not_hold() -> None:
    state = empty_state()
    state.frozen_analyzers = ("ruff",)
    state.diagnosis = _diagnosis(mypy_configured=True)
    rendered = render_quality(state, "", CURRENT)
    assert "- Analyzers: **ruff** (mypy is configured but not ratcheted)" in rendered


def test_quality_omits_the_marker_once_the_roster_covers_every_configured_analyzer() -> None:
    state = empty_state()
    state.frozen_analyzers = ("mypy", "ruff")
    state.diagnosis = _diagnosis(mypy_configured=True)
    rendered = render_quality(state, "", CURRENT)
    assert "configured but not ratcheted" not in rendered


def test_quality_never_invents_the_marker_without_a_diagnosis_to_compare_against() -> None:
    # A repository that never ran `diagnose` has nothing to compare its roster against —
    # inventing a complaint from missing data is what "absence and zero are different" forbids.
    state = empty_state()
    state.frozen_analyzers = ("ruff",)
    assert state.diagnosis is None
    rendered = render_quality(state, "", CURRENT)
    assert "configured but not ratcheted" not in rendered


def test_deferred_work_carries_the_commit_it_was_seen_at() -> None:
    state = append_log(empty_state(), "deferred", "router.py needs splitting", "abc12345", rule="C901")
    rendered = render_quality(state, "", CURRENT)
    assert "## Carried over" in rendered
    assert "router.py needs splitting" in rendered
    assert "abc12345" in rendered


def test_a_note_is_logged_but_is_not_carried_over() -> None:
    state = append_log(empty_state(), "note", "ran the first drain", "abc12345")
    rendered = render_quality(state, "", CURRENT)
    assert "## Carried over" not in rendered
    assert "## Work log" in rendered


def test_the_worklist_is_derived_from_state_not_stored() -> None:
    state = empty_state()
    state.diagnosed_at = "2026-08-01T00:00:00Z"
    state.frozen_at = "2026-08-02T00:00:00Z"
    state.rules = {"E501": RuleBaseline(baseline=3, current=3, status="draining")}
    lines = render_worklist(build_worklist(state))
    assert lines[0].startswith("- [x] **P0 diagnose**")
    assert lines[2].startswith("- [x] **P2 freeze**")
    assert any("`E501` — 3 left" in line for line in lines)


def test_drain_is_done_only_once_the_backlog_is_empty() -> None:
    state = empty_state()
    state.frozen_at = "2026-08-02T00:00:00Z"
    items = {item.label: item for item in build_worklist(state)}
    assert items["P3 drain"].done
    assert items["P3 drain"].detail == "backlog empty"


def test_next_says_so_rather_than_printing_an_empty_table() -> None:
    rendered = render_next(build_drain_plan([]))
    assert "Nothing is grandfathered here" in rendered


def test_next_reports_how_many_rows_it_did_not_show() -> None:
    entries = [Suppression(file=f"f{i}.py", rule="E501", count=1) for i in range(14)]
    rendered = render_next(build_drain_plan(entries))
    assert "+ 4 more" in rendered


def test_fan_in_is_shown_only_where_it_was_measured() -> None:
    entries = [Suppression(file="a.py", rule="E501", count=1), Suppression(file="b.py", rule="E501", count=1)]
    rendered = render_next(build_drain_plan(entries, importers={"a.py": 7, "b.py": 0}))
    assert "(imported by 7)" in rendered
    # Printing "imported by 0" reads as a measurement rather than as an absence.
    assert "(imported by 0)" not in rendered


def test_a_frozen_repository_with_nothing_to_grandfather_is_not_told_to_freeze() -> None:
    state = empty_state()
    state.frozen_at = "2026-08-02T00:00:00Z"
    rendered = render_quality(state, "", CURRENT)
    assert "the freeze found no violations" in rendered
    assert "Run `ebpy freeze`" not in rendered


def test_an_unfrozen_repository_is_told_to_freeze() -> None:
    assert "Run `ebpy freeze`" in render_quality(empty_state(), "", CURRENT)
