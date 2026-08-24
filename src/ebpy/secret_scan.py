"""Interpreting gitleaks, which answers three questions with two exit codes.

gitleaks reports "I found a secret" and "I could not run" with the same 1
unless a findings code is asked for, so every run passes ``--exit-code 2`` and
this reads three outcomes rather than two.
"""

from __future__ import annotations

from dataclasses import dataclass

CLEAN_EXIT_CODE = 0
SCAN_FAILED_EXIT_CODE = 1
SECRET_FINDING_EXIT_CODE = 2


@dataclass(frozen=True)
class SecretVerdict:
    """A secret scan's verdict: whether it is clean, its gitleaks-style exit code, and the message."""

    ok: bool
    # Mirrors gitleaks: 0 clean, 2 findings, 1 the scan itself failed. Collapsing them
    # loses the distinction the whole exit-code choice exists for.
    code: int
    message: str


# What a finding means depends on which scan found it, and the difference is the whole
# advice: a key in the history is already public and rotation is the only fix, while one
# sitting uncommitted has not been published yet and deleting it genuinely is enough.
FOUND_IN_HISTORY = (
    "Secrets found in the history. Rotate them — they are in every clone already, "
    "and removing the line does not un-publish them."
)
FOUND_IN_WORKING_TREE = (
    "Secrets found in files that are not committed yet. Remove them before committing; "
    "rotate as well if this tree was ever pushed or shared."
)

MISSING_GITLEAKS = "\n".join(
    [
        "gitleaks is not on PATH, so nothing was scanned — which is not the same as finding nothing.",
        "",
        "  brew install gitleaks",
        "  or a release binary: https://github.com/gitleaks/gitleaks/releases",
        "",
        "`ebpy bootstrap` writes a CI workflow that installs it for you; this command is for",
        "checking before you push.",
    ]
)

NOT_A_REPOSITORY = "\n".join(
    [
        "Not a git repository, so there is no history to scan — and that is not a clean result.",
        "",
        "`gitleaks git` here would report `no leaks found` after scanning zero commits, which is why",
        "this refuses rather than passing that on.",
    ]
)


def _joined(headline: str, output: str) -> str:
    parts = [headline, "", output.strip()]
    return "\n".join(part for part in parts if part)


def interpret_gitleaks(code: int, output: str, found: str = FOUND_IN_HISTORY) -> SecretVerdict:
    """Map a gitleaks exit code and output to a SecretVerdict, treating a failed scan as not clean."""
    if code == CLEAN_EXIT_CODE:
        return SecretVerdict(ok=True, code=CLEAN_EXIT_CODE, message="No secrets found.")
    if code == SECRET_FINDING_EXIT_CODE:
        return SecretVerdict(ok=False, code=SECRET_FINDING_EXIT_CODE, message=_joined(found, output))
    return SecretVerdict(
        ok=False,
        code=SCAN_FAILED_EXIT_CODE,
        message=_joined(
            f"gitleaks could not complete the scan (exit {code}). "
            "This is not a clean result — nothing was checked.",
            output,
        ),
    )


def combine_scans(verdicts: list[SecretVerdict]) -> SecretVerdict:
    """The worst verdict wins, and a scan that failed outranks a clean one: two scans
    run, and "one of them could not look" must not be reported as "nothing found".

    Every message survives, whichever code wins: a run that both found something and
    could not finish has two things worth acting on, and dropping the finding to
    report the failure loses the one that names a file.
    """
    bad = [verdict for verdict in verdicts if not verdict.ok]
    if not bad:
        return SecretVerdict(
            ok=True, code=CLEAN_EXIT_CODE, message="No secrets found — history and working tree both scanned."
        )
    failed = any(verdict.code == SCAN_FAILED_EXIT_CODE for verdict in bad)
    return SecretVerdict(
        ok=False,
        code=SCAN_FAILED_EXIT_CODE if failed else SECRET_FINDING_EXIT_CODE,
        message="\n\n".join(verdict.message for verdict in bad),
    )
