"""End-to-end lifecycle over a real repository and a real Ruff.

Diagnose, bootstrap, freeze, check, fix, prune. The ratchet's whole claim is that
the number can fall but never rise, and only a run over real tools tests that claim.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from ebpy.cli import main

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(shutil.which("ruff") is None, reason="needs a real ruff on PATH")

DIRTY = """\
import os


def handler(payload, unused_argument):
    result = payload["value"]
    if result == None:
        return  None
    return result
"""

CLEAN = '''\
"""A module the whole rule set passes, so fixing app.py empties its cell."""

from typing import Any


def handler(payload: dict[str, Any]) -> Any:
    """Return the payload's value."""
    return payload["value"]
'''


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(DIRTY, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n', encoding="utf-8"
    )
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


def run(repo: Path, *args: str) -> int:
    return main(["--cwd", str(repo), *args])


def test_diagnose_names_the_gaps_and_writes_nothing_without_write(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(repo, "diagnose") == 0
    assert "ruff" in capsys.readouterr().out
    assert not (repo / "QUALITY.md").exists()
    assert not (repo / ".ebpy").exists()


def test_diagnose_write_records_the_commit_it_was_taken_at(repo: Path) -> None:
    assert run(repo, "diagnose", "--write") == 0
    state = json.loads((repo / ".ebpy" / "state.json").read_text(encoding="utf-8"))
    assert state["diagnosedCommit"]
    assert (repo / "QUALITY.md").exists()


def test_bootstrap_writes_the_configs_it_promised(repo: Path) -> None:
    assert run(repo, "bootstrap") == 0
    pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.ruff]" in pyproject
    assert "[tool.mypy]" in pyproject
    assert (repo / ".github" / "workflows" / "quality.yml").exists()
    assert (repo / ".github" / "workflows" / "secret-scan.yml").exists()


def test_check_before_a_freeze_refuses_rather_than_passing(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "bootstrap")
    assert run(repo, "check") == 1
    assert "No baseline" in capsys.readouterr().out


def test_the_full_ratchet_cycle(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(repo, "bootstrap")

    assert run(repo, "freeze") == 0
    assert "grandfathered" in capsys.readouterr().out
    baseline = json.loads((repo / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    assert baseline["cells"]["src/app.py"]

    # Today's violations are exactly the ceiling, so the gate passes.
    assert run(repo, "check") == 0
    assert "Clean." in capsys.readouterr().out

    # A NEW file has no cell of its own, so its first violation is new — this is the
    # whole point of a per-file ratchet.
    (repo / "src" / "new.py").write_text(DIRTY, encoding="utf-8")
    assert run(repo, "check") == 1
    assert "beyond the ceiling" in capsys.readouterr().out
    (repo / "src" / "new.py").unlink()
    assert run(repo, "check") == 0
    capsys.readouterr()

    # Fixing the old file and pruning lowers the ceiling by exactly what was fixed.
    before = json.loads((repo / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    (repo / "src" / "app.py").write_text(CLEAN, encoding="utf-8")
    assert run(repo, "prune") == 0
    assert "Reclaimed" in capsys.readouterr().out
    after = json.loads((repo / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))
    assert after["cells"].get("src/app.py", {}) == {}

    # And the reclaimed ceiling holds: reintroducing the same code now fails.
    assert sum(entry["count"] for rules in before["cells"].values() for entry in rules.values()) > 0
    (repo / "src" / "app.py").write_text(DIRTY, encoding="utf-8")
    assert run(repo, "check") == 1


def test_freezing_twice_is_refused(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(repo, "bootstrap")
    run(repo, "freeze")
    capsys.readouterr()
    assert run(repo, "freeze") == 1
    output = capsys.readouterr().out
    assert "Already frozen" in output
    assert "prune" in output


def test_force_is_the_explicit_escape(repo: Path) -> None:
    run(repo, "bootstrap")
    run(repo, "freeze")
    (repo / "src" / "more.py").write_text(DIRTY, encoding="utf-8")
    assert run(repo, "freeze", "--force") == 0
    assert run(repo, "check") == 0


def test_next_ranks_the_backlog_after_a_freeze(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(repo, "bootstrap")
    run(repo, "freeze")
    capsys.readouterr()
    assert run(repo, "next", "--json") == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["totals"]["violations"] > 0
    assert plan["takeFirst"]


def test_report_refuses_when_a_fresh_repository_has_no_contract_to_show(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # No detected language and no frozen ceiling leaves nothing to report: printing
    # "# Analysis report" over that would render absence as zero.
    assert main(["--cwd", str(tmp_path), "report"]) == 1
    assert "No analyzer applies here" in capsys.readouterr().out


def test_report_survives_a_repository_that_cannot_lint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A report is not a gate: a detected language with no Ruff config and no baseline
    # still has standing — measuring today's findings against an empty ceiling — so it
    # still produces output.
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    assert main(["--cwd", str(tmp_path), "report"]) == 0
    assert "# Analysis report" in capsys.readouterr().out


def test_log_writes_the_work_log_nothing_else_does(repo: Path) -> None:
    assert run(repo, "log", "--kind", "deferred", "--rule", "ruff:C901", "router.py is its own project") == 0
    quality = (repo / "QUALITY.md").read_text(encoding="utf-8")
    assert "## Carried over" in quality
    assert "router.py is its own project" in quality


def test_an_unknown_log_kind_is_refused(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(repo, "log", "--kind", "whatever", "text") == 1
    assert "--kind must be one of" in capsys.readouterr().out


def test_notes_written_by_hand_survive_a_re_render(repo: Path) -> None:
    run(repo, "diagnose", "--write")
    quality = repo / "QUALITY.md"
    text = quality.read_text(encoding="utf-8").replace(
        "_Anything written between these markers survives a re-render._",
        "migrations/ is generated; E501 there is not ours",
    )
    quality.write_text(text, encoding="utf-8")
    run(repo, "diagnose", "--write")
    assert "migrations/ is generated" in quality.read_text(encoding="utf-8")


def test_catalog_lists_the_helpers(repo: Path) -> None:
    (repo / "src" / "util.py").write_text(
        '''def shared() -> None:
    """Does the shared thing."""
''',
        encoding="utf-8",
    )
    assert run(repo, "catalog") == 0
    catalog = (repo / "docs" / "shared-helpers.md").read_text(encoding="utf-8")
    assert "`shared`" in catalog
    assert "Does the shared thing." in catalog


def test_status_reads_the_ledger(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(repo, "bootstrap")
    run(repo, "freeze")
    capsys.readouterr()
    assert run(repo, "status") == 0
    output = capsys.readouterr().out
    assert "phase      drain" in output
    assert "smallest remaining backlogs:" in output


def test_status_outside_an_initialised_repo_says_where_to_start(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--cwd", str(tmp_path), "status"]) == 0
    assert "Start with `ebpy diagnose`" in capsys.readouterr().out
