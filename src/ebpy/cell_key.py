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

    "Absolute" is judged lexically in both path flavours so the classification does not
    depend on the host OS. The repository-relative containment test uses the host-native
    `Path`, because only a path this host can itself resolve — a POSIX path on a POSIX host,
    a drive-qualified path on a Windows host — could denote a location under `cwd`. A path
    that is absolute only in the foreign flavour (a Windows drive path seen on POSIX, or a
    POSIX-rooted path seen on Windows) can never be under `cwd`, so it is left absolute
    rather than misread by a `Path.resolve()` that treats it as relative.
    """
    slashed = filename.replace("\\", "/")
    if not PureWindowsPath(slashed).is_absolute() and not PurePosixPath(slashed).is_absolute():
        return PurePosixPath(slashed).as_posix()
    if Path(slashed).is_absolute():
        try:
            relative = Path(slashed).resolve().relative_to(cwd.resolve())
        except ValueError:
            pass
        else:
            return PurePosixPath(*relative.parts).as_posix()
    return PurePosixPath(slashed).as_posix()
