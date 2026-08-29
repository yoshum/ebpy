"""Whether this run's unmeasured packages narrow the frozen contract."""

from __future__ import annotations

from ebpy.decide.unmeasured import next_unmeasured_packages, unmeasured_verdict
from ebpy.measurement import Failed, Measured, Measurement
from ebpy.models import AnalysisMeasurement, State, UnmeasuredScope


def _measurement(*scopes: UnmeasuredScope) -> Measurement:
    return Measurement(
        {"clippy": Measured(tool="clippy", value=AnalysisMeasurement(cells={}, unmeasured=scopes))}
    )


def _scope(root: str, *packages: str) -> UnmeasuredScope:
    return UnmeasuredScope(root=root, packages=packages or (root,))


def test_a_range_that_was_never_covered_passes() -> None:
    """Tokio's shape: a fuzz workspace that never compiled in this configuration."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    assert not unmeasured_verdict(_measurement(_scope("fuzz")), state, {}).regressed


def test_a_package_that_was_covered_and_is_no_longer_fails_closed() -> None:
    """The cells cannot answer this: a clean workspace writes none, exactly like an unmeasured one."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    verdict = unmeasured_verdict(_measurement(_scope(".", "fuzz", "core")), state, {})
    assert verdict.regressed


def test_a_workspace_root_staying_the_same_does_not_hide_a_moved_package() -> None:
    """`members` and `exclude` move packages across an unchanged root; roots cannot see that."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    verdict = unmeasured_verdict(_measurement(_scope(".", "fuzz", "core")), state, {})
    assert verdict.regressed
    assert verdict.scopes[0].root == "."


def test_coverage_widening_passes_and_updates_the_contract() -> None:
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    verdict = unmeasured_verdict(_measurement(), state, {})
    assert not verdict.regressed
    assert next_unmeasured_packages(state, verdict) == ()


def test_deleting_a_crate_is_never_a_regression() -> None:
    """Remembering the measured set instead would demand a --force for every deletion."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    assert not unmeasured_verdict(_measurement(_scope("fuzz")), state, {}).regressed


def test_a_repository_that_does_not_ratchet_clippy_never_regresses() -> None:
    """Otherwise a Python repository's check fails because of a Rust fuzz workspace."""
    state = State(frozen_analyzers=("ruff", "mypy"))
    assert not unmeasured_verdict(_measurement(_scope("fuzz")), state, {}).regressed


def test_a_failed_run_carries_the_previous_contract_rather_than_emptying_it() -> None:
    """A run that never happened must not record "nothing is excluded"."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    measurement = Measurement({"clippy": Failed(tool="clippy", failure_kind="execution-failed", detail="x")})
    verdict = unmeasured_verdict(measurement, state, {})
    assert not verdict.measured
    assert next_unmeasured_packages(state, verdict) == ("fuzz",)


def test_a_run_that_did_not_measure_clippy_at_all_carries_the_contract() -> None:
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    verdict = unmeasured_verdict(Measurement({}), state, {})
    assert next_unmeasured_packages(state, verdict) == ("fuzz",)


def test_the_cells_at_stake_are_named_from_the_newly_dropped_packages() -> None:
    """Judgment is set containment; naming is an approximation, and that split is deliberate."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=())
    baseline = {"core/src/lib.rs": {"clippy:clippy::x": 3}, "other/src/lib.rs": {"clippy:clippy::y": 1}}
    verdict = unmeasured_verdict(_measurement(_scope("core")), state, baseline)
    assert verdict.regressed
    assert any("core/src/lib.rs" in cell for cell in verdict.lost_cells)
