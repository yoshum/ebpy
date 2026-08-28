"""ScopeDecision: what gets measured, and when the three authorities disagree."""

from __future__ import annotations

from ebpy.decide.analyzer_scope import ScopeDecision, empty_scope_message, scope_decision
from ebpy.models import State
from ebpy.repo.detect.language import RepoLanguages
from ebpy.store.config import EbpyConfig

REGISTERED = frozenset({"ruff", "mypy", "clippy"})


def _decision(
    declared: frozenset[str] | None = None,
    detected: frozenset[str] = frozenset(),
    frozen: frozenset[str] = frozenset(),
) -> ScopeDecision:
    return ScopeDecision(
        declared=declared,
        detected_analyzers=detected,
        frozen=frozen,
        registered_analyzers=REGISTERED,
    )


def test_a_declared_set_is_what_gets_measured() -> None:
    assert _decision(declared=frozenset({"ruff"}), detected=frozenset({"ruff", "mypy"})).to_measure == (
        "ruff",
    )


def test_without_a_config_the_detected_set_is_what_gets_measured() -> None:
    assert _decision(detected=frozenset({"mypy", "ruff"})).to_measure == ("mypy", "ruff")


def test_a_fresh_repository_never_reports_a_mismatch() -> None:
    """Reconciling against an empty roster would make every declared analyzer a mismatch."""
    decision = _decision(declared=frozenset({"ruff", "mypy"}))
    assert decision.mismatch() is None
    assert decision.scope_mismatches == frozenset()


def test_a_declared_set_must_match_the_contract_in_both_directions() -> None:
    declared_not_frozen = _decision(declared=frozenset({"ruff", "mypy"}), frozen=frozenset({"ruff"}))
    frozen_not_declared = _decision(declared=frozenset({"ruff"}), frozen=frozenset({"ruff", "mypy"}))
    assert declared_not_frozen.scope_mismatches == frozenset({"mypy"})
    assert frozen_not_declared.scope_mismatches == frozenset({"mypy"})
    assert "mypy" in (declared_not_frozen.mismatch() or "")
    assert "mypy" in (frozen_not_declared.mismatch() or "")


def test_a_detected_set_is_reconciled_in_one_direction_only() -> None:
    """Detected-but-unfrozen is a diagnose gap, not an error; frozen-but-undetected fails closed."""
    unfrozen = _decision(detected=frozenset({"ruff", "mypy"}), frozen=frozenset({"ruff"}))
    undetected = _decision(detected=frozenset({"ruff"}), frozen=frozenset({"ruff", "clippy"}))
    assert unfrozen.mismatch() is None
    assert undetected.scope_mismatches == frozenset({"clippy"})


def test_an_unregistered_frozen_analyzer_stays_a_no_runner_case() -> None:
    """`pylint` in the contract must reach classify(None), not be renamed a scope mismatch."""
    decision = _decision(detected=frozenset({"ruff"}), frozen=frozenset({"ruff", "pylint"}))
    assert decision.scope_mismatches == frozenset()
    assert decision.mismatch() is None


def test_reconciliation_does_not_depend_on_ordering() -> None:
    """The projection comes out in registry order and the roster comes out sorted."""
    decision = _decision(detected=frozenset({"ruff", "mypy"}), frozen=frozenset({"mypy", "ruff"}))
    assert decision.mismatch() is None


def test_a_forced_freeze_without_a_config_keeps_the_existing_contract() -> None:
    """Deleting Cargo.toml must not drop clippy from the contract just because nothing declared it."""
    decision = _decision(detected=frozenset(), frozen=frozenset({"clippy"}))
    assert decision.to_measure == ()
    assert decision.global_freeze_scope == ("clippy",)


def test_a_declared_set_is_the_whole_freeze_scope() -> None:
    """Narrowing the config and forcing is the one deliberate way to shrink the contract."""
    decision = _decision(declared=frozenset({"ruff"}), frozen=frozenset({"ruff", "mypy"}))
    assert decision.global_freeze_scope == ("ruff",)


def test_scope_decision_projects_languages_onto_analyzer_names() -> None:
    state = State(frozen_analyzers=("ruff",))
    decision = scope_decision(None, RepoLanguages(frozenset({"python"})), state)
    assert "ruff" in decision.detected_analyzers
    assert "clippy" not in decision.detected_analyzers
    assert decision.frozen == frozenset({"ruff"})


def test_scope_decision_reads_the_declared_set_from_the_config() -> None:
    decision = scope_decision(
        EbpyConfig(analyzers=("mypy", "ruff")), RepoLanguages(frozenset({"python"})), State()
    )
    assert decision.declared == frozenset({"mypy", "ruff"})


def test_the_empty_scope_message_names_what_was_looked_for() -> None:
    message = empty_scope_message(_decision())
    assert "no analyzer" in message.lower()
    assert ".ebpy/config.json" in message
