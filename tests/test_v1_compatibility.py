"""Pin the v1 -> v2 artifact boundary through the real reader `read_ceiling_artifacts`.

All tests write on-disk fixtures into `tmp_path`, never touching production code.
The boundary rule: a v1 state with mypy:errors {0, 0} + frozenAt normalises to a frozen
two-analyzer contract; any other counter value or name makes the whole state unreadable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ebpy.baseline import baseline_path
from ebpy.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
from ebpy.commands import check as check_command
from ebpy.commands.check import run_check
from ebpy.measurement import Measured, Measurement
from ebpy.models import AnalysisMeasurement
from ebpy.state import state_path

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FROZEN_AT = "2026-08-19T00:00:00Z"

# A single ruff rule used across fixtures; one cell keeps all assertions simple.
_RULE_LOCAL = "F401"
_RULE_ID = "ruff:F401"
_FILE = "src/app.py"
_COUNT = 2


def _write_v1_state(
    cwd: Path,
    *,
    counters: dict[str, Any] | None = None,
    frozen_at: str | None = _FROZEN_AT,
    rules: dict[str, Any] | None = None,
) -> None:
    """Write a minimal v1 state.json with caller-supplied counters."""
    raw: dict[str, Any] = {
        "version": 1,
        "tool": "ebpy",
        "phase": "drain",
        "updatedAt": _FROZEN_AT,
        "frozenAt": frozen_at,
        "diagnosedAt": None,
        "diagnosedCommit": None,
        "diagnosis": None,
        "rules": rules
        if rules is not None
        else {_RULE_LOCAL: {"baseline": _COUNT, "current": _COUNT, "status": "draining"}},
        "counters": counters if counters is not None else {},
        "log": [],
    }
    path = state_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw) + "\n", encoding="utf-8")


def _write_v1_baseline(cwd: Path) -> None:
    """Write a v1 baseline.json using bare (unnamespaced) rule keys."""
    raw = {_FILE: {_RULE_LOCAL: {"count": _COUNT}}}
    path = baseline_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw) + "\n", encoding="utf-8")


def _valid_v1_pair(cwd: Path, *, counters: dict[str, Any] | None = None) -> None:
    """Write a coherent v1 pair: bare baseline + state with mypy:errors {0, 0}."""
    _write_v1_baseline(cwd)
    _write_v1_state(
        cwd,
        counters=counters if counters is not None else {"mypy:errors": {"baseline": 0, "current": 0}},
    )


def _measured_clean(analyzer: str) -> Measured[AnalysisMeasurement]:
    return Measured(tool=analyzer, value=AnalysisMeasurement(cells={}))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_a_zero_mypy_counter_pair_reads_as_a_frozen_two_analyzer_contract(tmp_path: Path) -> None:
    """A v1 pair whose only counter is mypy:errors {0, 0} and whose state has frozenAt set
    normalises to a frozen contract covering both ruff and mypy."""
    _valid_v1_pair(tmp_path)

    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "frozen"
    assert artifacts.ledger.state is not None
    assert set(artifacts.ledger.state.frozen_analyzers) == {"mypy", "ruff"}


def test_a_mypy_counter_of_one_over_one_is_refused(tmp_path: Path) -> None:
    """A v1 state whose mypy:errors counter records baseline=1, current=1 cannot be decomposed
    into file x rule cells, so reading it returns kind='invalid'."""
    _write_v1_baseline(tmp_path)
    _write_v1_state(tmp_path, counters={"mypy:errors": {"baseline": 1, "current": 1}})

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_a_mypy_counter_of_zero_over_one_is_refused(tmp_path: Path) -> None:
    """A nonzero current in mypy:errors is undecomposable regardless of whether the baseline
    is zero — the current count would have to be invented as a distribution."""
    _write_v1_baseline(tmp_path)
    _write_v1_state(tmp_path, counters={"mypy:errors": {"baseline": 0, "current": 1}})

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_a_mypy_counter_of_one_over_zero_is_refused_though_the_total_improved(tmp_path: Path) -> None:
    """A nonzero baseline in mypy:errors makes the state unreadable even though current
    dropped to zero — the baseline was a real ceiling that cannot be redistributed."""
    _write_v1_baseline(tmp_path)
    _write_v1_state(tmp_path, counters={"mypy:errors": {"baseline": 1, "current": 0}})

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_an_unknown_v1_counter_is_refused(tmp_path: Path) -> None:
    """A counter whose name is not 'mypy:errors' produces no cell model to migrate to,
    so any unknown counter name makes the whole state unreadable."""
    _write_v1_baseline(tmp_path)
    _write_v1_state(tmp_path, counters={"other:thing": {"baseline": 0, "current": 0}})

    assert read_ceiling_artifacts(tmp_path).kind == "invalid"


def test_the_refusal_names_restoring_matching_artifacts_and_freeze_force(tmp_path: Path) -> None:
    """The invalid-artifacts message tells the user both how to restore the matching pair and
    that 'ebpy freeze --force' is the escape hatch — both pieces must appear so the user has
    a path forward."""
    _write_v1_baseline(tmp_path)
    _write_v1_state(tmp_path, counters={"mypy:errors": {"baseline": 1, "current": 1}})
    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "invalid"
    message = invalid_artifacts_message(artifacts)

    assert "Restore" in message
    assert "ebpy freeze --force" in message


def test_reading_a_v1_pair_leaves_both_files_byte_identical(tmp_path: Path) -> None:
    """read_ceiling_artifacts is a pure read — it must not modify either artifact file,
    even though it normalises the in-memory State from v1 to v2 format."""
    _valid_v1_pair(tmp_path)
    baseline_before = baseline_path(tmp_path).read_bytes()
    state_before = state_path(tmp_path).read_bytes()

    read_ceiling_artifacts(tmp_path)

    assert baseline_path(tmp_path).read_bytes() == baseline_before
    assert state_path(tmp_path).read_bytes() == state_before


def test_the_first_check_write_on_a_v1_pair_upgrades_only_the_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_check with write=True upgrades state.json from v1 to v2 format while leaving
    baseline.json byte-identical — write_cells is never called by the check command."""
    _valid_v1_pair(tmp_path)
    baseline_before = baseline_path(tmp_path).read_bytes()

    # Inject a clean measurement so the check does not try to run real tools.
    monkeypatch.setattr(
        check_command,
        "measure_repository",
        lambda _cwd: Measurement(
            analyzers={
                "ruff": _measured_clean("ruff"),
                "mypy": _measured_clean("mypy"),
            }
        ),
    )
    run_check(tmp_path, write=True)

    # baseline is unchanged
    assert baseline_path(tmp_path).read_bytes() == baseline_before

    # state is now version 2
    upgraded = json.loads(state_path(tmp_path).read_text(encoding="utf-8"))
    assert upgraded["version"] == 2


def test_the_mixed_pair_left_by_that_check_is_valid_for_the_next_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the first check upgrades state.json to v2, the pair (v1 baseline + v2 state)
    must still classify as 'frozen' on the next read — the mixed pair is a valid ceiling."""
    _valid_v1_pair(tmp_path)
    monkeypatch.setattr(
        check_command,
        "measure_repository",
        lambda _cwd: Measurement(
            analyzers={
                "ruff": _measured_clean("ruff"),
                "mypy": _measured_clean("mypy"),
            }
        ),
    )
    run_check(tmp_path, write=True)

    artifacts = read_ceiling_artifacts(tmp_path)

    assert artifacts.kind == "frozen"


def test_this_repositorys_own_artifacts_are_version_two_and_agree() -> None:
    """The repository's own .ebpy/baseline.json and .ebpy/state.json must be version 2 and
    must classify as a valid frozen contract — the tool eats its own cooking."""
    repo_root = Path(__file__).resolve().parents[1]

    baseline_raw = json.loads((repo_root / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    state_raw = json.loads((repo_root / ".ebpy" / "state.json").read_text(encoding="utf-8"))

    assert baseline_raw.get("version") == 2
    assert state_raw.get("version") == 2

    artifacts = read_ceiling_artifacts(repo_root)
    assert artifacts.kind != "invalid"
