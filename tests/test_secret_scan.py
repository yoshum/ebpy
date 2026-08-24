"""The secret-scan verdict: clean, a finding, or a scan that failed, and how two scans combine."""

from __future__ import annotations

from ebpy.secret_scan import (
    FOUND_IN_WORKING_TREE,
    SecretVerdict,
    combine_scans,
    interpret_gitleaks,
)


def test_zero_is_clean() -> None:
    verdict = interpret_gitleaks(0, "")
    assert verdict.ok
    assert verdict.code == 0


def test_two_is_a_finding_and_says_rotation_is_the_fix() -> None:
    verdict = interpret_gitleaks(2, "aws key in config.py")
    assert not verdict.ok
    assert verdict.code == 2
    assert "Rotate them" in verdict.message
    assert "aws key in config.py" in verdict.message


def test_a_working_tree_finding_gets_the_other_advice() -> None:
    verdict = interpret_gitleaks(2, "key in .env", FOUND_IN_WORKING_TREE)
    assert "before committing" in verdict.message


def test_anything_else_is_a_scan_that_could_not_run() -> None:
    # gitleaks answers "I found a secret" and "I could not run" with the same 1 unless
    # a findings code is asked for — this is the half that is not a clean result.
    verdict = interpret_gitleaks(1, "failed to open repository")
    assert not verdict.ok
    assert verdict.code == 1
    assert "not a clean result" in verdict.message


def test_two_clean_scans_combine_clean() -> None:
    combined = combine_scans([interpret_gitleaks(0, ""), interpret_gitleaks(0, "")])
    assert combined.ok
    assert "history and working tree both scanned" in combined.message


def test_a_scan_that_failed_outranks_a_clean_one() -> None:
    combined = combine_scans([interpret_gitleaks(0, ""), interpret_gitleaks(1, "boom")])
    assert combined.code == 1


def test_a_failure_outranks_a_finding_but_keeps_both_messages() -> None:
    # A run that both found something and could not finish has two things worth acting
    # on; dropping the finding would lose the one that names a file.
    combined = combine_scans(
        [interpret_gitleaks(2, "key in config.py"), interpret_gitleaks(1, "could not read history")]
    )
    assert combined.code == 1
    assert "key in config.py" in combined.message
    assert "could not read history" in combined.message


def test_findings_alone_report_the_findings_code() -> None:
    combined = combine_scans([interpret_gitleaks(2, "key"), SecretVerdict(ok=True, code=0, message="")])
    assert combined.code == 2
