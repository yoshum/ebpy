"""End-to-end lifecycle over a real Cargo repository.

The ratchet's "can fall, never rise" claim has to hold for clippy cells too. Each test builds
its own fixture and drives the CLI through one complete sub-arc. These are slow because they
compile Rust; keep every fixture to one tiny crate.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from ebpy.cli import main
from ebpy.store.state import read_ledger

if TYPE_CHECKING:
    from pathlib import Path


def _clippy_available() -> bool:
    """Skip on clippy, not on cargo: a minimal rustup profile has cargo and no clippy component."""
    if shutil.which("cargo") is None:
        return False
    probe = subprocess.run(["cargo", "clippy", "--version"], capture_output=True, text=True, check=False)
    return probe.returncode == 0 and probe.stdout.startswith("clippy ")


pytestmark = pytest.mark.skipif(
    not _clippy_available(), reason="needs a toolchain whose `cargo clippy --version` succeeds"
)

_MANIFEST = "[package]\nname = 'demo'\nversion = '0.1.0'\nedition = '2021'\n"

# `needless_return` is among clippy's oldest and most stable lints, so the expected counts
# depend on the code rather than on which toolchain happens to be installed.
_DIRTY = "pub fn a() -> i32 {\n    return 1;\n}\n\npub fn b() -> i32 {\n    return 2;\n}\n"
_CLEAN = "pub fn a() -> i32 {\n    1\n}\n\npub fn b() -> i32 {\n    2\n}\n"

_RULE = "clippy:clippy::needless_return"


def _crate(root: Path, body: str) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(_MANIFEST, encoding="utf-8")
    (root / "src" / "lib.rs").write_text(body, encoding="utf-8")


def _cells(root: Path) -> dict[str, dict[str, int]]:
    # baseline.json stores each cell as {"count": N}, not a bare int (see
    # ebpy.store.baseline.BASELINE_VERSION 2) — unwrapped here so callers compare plain ints,
    # matching the convention tests/test_lifecycle.py and tests/test_baseline.py already use.
    raw = json.loads((root / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))["cells"]
    return {file: {rule: entry["count"] for rule, entry in rules.items()} for file, rules in raw.items()}


def test_freeze_pins_todays_clippy_warnings_as_the_ceiling(tmp_path: Path) -> None:
    _crate(tmp_path, _DIRTY)
    assert main(["freeze", "--cwd", str(tmp_path)]) == 0
    assert _cells(tmp_path)["src/lib.rs"][_RULE] == 2
    state = read_ledger(tmp_path).state
    assert state is not None
    assert state.frozen_analyzers == ("clippy",)


def test_check_passes_at_the_ceiling_and_fails_above_it(tmp_path: Path) -> None:
    _crate(tmp_path, _DIRTY)
    main(["freeze", "--cwd", str(tmp_path)])
    assert main(["check", "--cwd", str(tmp_path)]) == 0
    (tmp_path / "src" / "lib.rs").write_text(
        _DIRTY + "\npub fn c() -> i32 {\n    return 3;\n}\n", encoding="utf-8"
    )
    assert main(["check", "--cwd", str(tmp_path)]) != 0


def test_a_second_measurement_of_an_unchanged_repository_counts_the_same(tmp_path: Path) -> None:
    """Cargo re-emits saved diagnostics for units it did not recompile.

    Observed only — no documentation was found for it, and this area historically carried
    "no warnings on the second run" bugs. Splitting the target directory does not help,
    because the second run is still not recompiled, and `cargo clean` every time is not
    affordable. So the premise becomes an invariant CI holds.

    If a future cargo makes this fail, DO NOT adjust the expected value to the observed one.
    What is contracted here is not the number 2; it is that ebpy may rely on re-emission at
    all. A failure means that premise broke and the measurement strategy has to change —
    measure cold every time, or stop depending on re-emission. Rewriting 2 to 0 (or any other
    smaller number) would leave a ceiling that silently stops holding.
    """
    _crate(tmp_path, _DIRTY)
    main(["freeze", "--cwd", str(tmp_path)])
    first = _cells(tmp_path)["src/lib.rs"][_RULE]
    assert main(["freeze", "--force", "--cwd", str(tmp_path)]) == 0
    assert _cells(tmp_path)["src/lib.rs"][_RULE] == first


def test_prune_lowers_the_ceiling_after_a_fix_and_never_raises_it(tmp_path: Path) -> None:
    _crate(tmp_path, _DIRTY)
    main(["freeze", "--cwd", str(tmp_path)])
    (tmp_path / "src" / "lib.rs").write_text(_CLEAN, encoding="utf-8")
    assert main(["prune", "--cwd", str(tmp_path)]) == 0
    assert _cells(tmp_path) == {}
    (tmp_path / "src" / "lib.rs").write_text(_DIRTY, encoding="utf-8")
    assert main(["check", "--cwd", str(tmp_path)]) != 0


def test_a_rule_id_keeps_its_clippy_prefix_through_the_work_log(tmp_path: Path) -> None:
    """`split_rule` splits on the first colon only, so a local code may hold colons itself."""
    _crate(tmp_path, _DIRTY)
    main(["freeze", "--cwd", str(tmp_path)])
    assert main(["log", "--kind", "drained", "fixed one", "--rule", _RULE, "--cwd", str(tmp_path)]) == 0


@pytest.mark.skipif(
    shutil.which("ruff") is None or shutil.which("mypy") is None,
    reason="needs real ruff and mypy on PATH",
)
def test_a_mixed_repository_freezes_every_analyzer_together(tmp_path: Path) -> None:
    _crate(tmp_path, _DIRTY)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n", encoding="utf-8")
    (tmp_path / "mod.py").write_text("import os\n", encoding="utf-8")
    assert main(["freeze", "--cwd", str(tmp_path)]) == 0
    state = read_ledger(tmp_path).state
    assert state is not None
    assert set(state.frozen_analyzers) == {"clippy", "mypy", "ruff"}
