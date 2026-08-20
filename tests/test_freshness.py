from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ebpy.decide.freshness import FreshnessInput, assess_freshness

NOW = datetime(2026, 8, 17, tzinfo=UTC)


def at(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def make(**overrides: object) -> FreshnessInput:
    base = {
        "diagnosed_at": at(1),
        "diagnosed_commit": "abc1234",
        "head_commit": "abc1234",
        "commits_since": 0,
        "now": NOW,
    }
    base.update(overrides)
    return FreshnessInput(**base)  # type: ignore[arg-type]


def test_a_fresh_diagnosis_is_current() -> None:
    assert not assess_freshness(make()).stale


def test_never_diagnosed_is_stale_and_says_what_to_run() -> None:
    verdict = assess_freshness(make(diagnosed_at=None, diagnosed_commit=None))
    assert verdict.stale
    assert "diagnose" in verdict.reason


def test_an_old_diagnosis_goes_stale_on_age() -> None:
    verdict = assess_freshness(make(diagnosed_at=at(45)))
    assert verdict.stale
    assert "45 days old" in verdict.reason


def test_enough_commits_go_stale_even_when_recent() -> None:
    verdict = assess_freshness(make(commits_since=120))
    assert verdict.stale
    assert "120 commits" in verdict.reason


def test_a_commit_no_longer_in_this_history_is_stale() -> None:
    # After a rebase or force-push the distance cannot be computed, which is itself a
    # reason to re-diagnose rather than a number to guess at.
    verdict = assess_freshness(make(head_commit="deadbee", commits_since=None))
    assert verdict.stale
    assert "distance is unknown" in verdict.reason


def test_an_unparseable_timestamp_does_not_crash_the_age_check() -> None:
    assert not assess_freshness(make(diagnosed_at="whenever")).stale
