"""The identity of a ratchet cell: a namespaced rule ID and a normalized file path.

A cell is keyed by `<file>` x `<analyzer>:<local-code>`. Both halves of that key are owned
here so that no other module has to reinvent either spelling. Before this module existed,
`ruff_runner.py` and `baseline.py` each normalized paths on their own (`_relative_posix` and
`_to_posix`); if a runner and the reader that later compares its output ever disagreed on
either half — how a rule is namespaced, or how a path is normalized — the same finding would
be recorded as two different cells, and the ratchet would silently stop holding it.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

ANALYZER_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")


def is_analyzer_name(name: str) -> bool:
    return ANALYZER_NAME.fullmatch(name) is not None


def qualify_rule(analyzer: str, local_code: str) -> str:
    if not is_analyzer_name(analyzer):
        raise ValueError(f"not a valid analyzer name: {analyzer!r}")
    if not local_code or "\n" in local_code or "\r" in local_code:
        raise ValueError(f"not a valid local rule code: {local_code!r}")
    return f"{analyzer}:{local_code}"


def _partition(rule: str) -> tuple[str, str] | None:
    analyzer, separator, local_code = rule.partition(":")
    if (
        not separator
        or not local_code
        or "\n" in local_code
        or "\r" in local_code
        or not is_analyzer_name(analyzer)
    ):
        return None
    return analyzer, local_code


def split_rule(rule: str) -> tuple[str, str]:
    """Split on the first colon only, so a local code may itself contain colons."""
    parsed = _partition(rule)
    if parsed is None:
        raise ValueError(f"not a namespaced rule id: {rule!r}")
    return parsed


def analyzer_of(rule: str) -> str:
    return split_rule(rule)[0]


def is_rule_id(value: object) -> bool:
    """The total predicate persistence readers use on untrusted JSON: never raises."""
    return isinstance(value, str) and _partition(value) is not None


def normalize_analyzer_path(filename: str, cwd: Path) -> str:
    """Normalize a path an analyzer reported into the form a stored cell key uses.

    Classification of "absolute" is done lexically with `PureWindowsPath` / `PurePosixPath`
    so the result does not depend on the host OS running the tool. Only a path this host's
    real filesystem could itself resolve — a POSIX-absolute path on a POSIX host — goes
    through `Path.resolve()` for the repository-relative containment test; a Windows
    drive-qualified path can never denote a location under a POSIX `cwd`, so it is left
    absolute rather than fed to a `Path.resolve()` that would misread it as relative.
    """
    slashed = filename.replace("\\", "/")
    if PureWindowsPath(slashed).is_absolute():
        return PureWindowsPath(slashed).as_posix()
    posix = PurePosixPath(slashed)
    if not posix.is_absolute():
        return str(posix)
    try:
        relative = Path(slashed).resolve().relative_to(cwd.resolve())
    except ValueError:
        return str(posix)
    return str(PurePosixPath(*relative.parts))
