"""Commands fail consistently when the ceiling artifacts are invalid."""

from __future__ import annotations

from pathlib import Path

import pytest

from ebpy.baseline import write_cells
from ebpy.cli import main
from ebpy.state import state_path


@pytest.mark.parametrize(
    "args",
    [
        ("diagnose", "--write"),
        ("log", "a note that must not replace the ledger"),
    ],
)
def test_an_unreadable_ledger_is_never_replaced(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    args: tuple[str, ...],
) -> None:
    path = state_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe")
    quality = tmp_path / "QUALITY.md"
    quality.write_text("existing report\n", encoding="utf-8")

    assert main(["--cwd", str(tmp_path), *args]) == 1

    assert "Ceiling artifacts are invalid" in capsys.readouterr().out
    assert path.read_bytes() == b"\xff\xfe"
    assert quality.read_text(encoding="utf-8") == "existing report\n"


@pytest.mark.parametrize(
    "args",
    [
        ("diagnose", "--write"),
        ("log", "a note"),
        ("check", "--no-write"),
        ("status",),
        ("next",),
        ("report",),
    ],
)
def test_an_incomplete_ceiling_pair_fails_every_command_that_uses_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    args: tuple[str, ...],
) -> None:
    write_cells(tmp_path, {})

    assert main(["--cwd", str(tmp_path), *args]) == 1
    assert "Ceiling artifacts are invalid" in capsys.readouterr().out
