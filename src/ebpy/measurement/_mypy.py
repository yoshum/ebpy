"""Runs the target repo's own mypy and turns its findings into cells, like Ruff's.

Each error line becomes one cell keyed `mypy:<code>`, aggregated per file — the same
shape Ruff's runner produces — so a type error can share a per-file per-rule ceiling
with lint violations instead of being tracked as a single undifferentiated total.
"""

from __future__ import annotations

import configparser
import re
import shutil
import tomllib
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from ..cell_key import normalize_analyzer_path, qualify_rule
from ..errors import ToolError
from ..models import AnalysisMeasurement, CellCounts
from ..util import run

# The location prefix of an error line: `<file>:<line>[:<column>[:<end-line>:<end-column>]]: error: `.
# This is what marks a line as an error mypy is reporting, as opposed to a `note:` whose own
# message text happens to contain the substring `: error: `. Screening on the substring alone
# would drag such a note into the strict parse below and refuse the whole measurement over a
# line that was never an error. The filename group is non-greedy; see `_MYPY_ERROR_LINE`.
_MYPY_ERROR_PREFIX = re.compile(
    r"^.+?:\d+(?::\d+)?(?::\d+:\d+)?: error: ",
)

# A fully parseable error line: the prefix above followed by `<message>  [<code>]`.
# The filename group is non-greedy. mypy's own filenames can contain a colon — a Windows
# drive letter, or a literal colon in the path — so a greedy group would swallow the first
# `: error: ` it could find instead of the real one. Backtracking from the left lets the
# engine walk the filename forward past a false location match until it reaches the digit
# groups that are actually followed by `: error: `.
_MYPY_ERROR_LINE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+)"
    r"(?::(?P<column>\d+))?"
    r"(?::(?P<end_line>\d+):(?P<end_column>\d+))?"
    r": error: (?P<message>.*?)\s+\[(?P<code>[^\[\]\s]+)\]$"
)

# Long enough for a config error or a missing-stubs line, short enough to stay one line.
_SUMMARY_LIMIT = 200


class MypyNotFoundError(ToolError):
    pass


class MypyFailedError(ToolError):
    pass


class MypyInvalidOutputError(MypyFailedError):
    pass


def find_mypy(cwd: Path) -> list[str] | None:
    for venv in (".venv", "venv"):
        for bindir, exe in (("bin", "mypy"), ("Scripts", "mypy.exe")):
            candidate = cwd / venv / bindir / exe
            if candidate.is_file():
                return [str(candidate)]
    on_path = shutil.which("mypy")
    return [on_path] if on_path else None


# The keys by which a mypy config names its own check target. Any one of them makes the
# config self-sufficient about what to check, so a positional `.` would only override it.
_SELECTION_KEYS = ("files", "packages", "modules")

# mypy's own config-file search order (relative to cwd): the first that exists and carries
# a mypy section wins, and later files are never consulted. Matching that order here means
# ebpy reads the same file mypy would, not a different one that happens to sort first.
_CONFIG_FILES = ("mypy.ini", ".mypy.ini", "pyproject.toml", "setup.cfg")


def _toml_selects_target(text: str) -> bool | None:
    """Whether `[tool.mypy]` in a pyproject names a check target; None if there is no table."""
    try:
        data: Any = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    table = ((data.get("tool") or {}).get("mypy")) if isinstance(data, dict) else None
    if not isinstance(table, dict):
        return None
    return any(key in table for key in _SELECTION_KEYS)


def _ini_selects_target(text: str, section: str) -> bool | None:
    """Whether an ini `section` names a check target; None if the section is absent."""
    parser = configparser.ConfigParser()
    try:
        parser.read_string(text)
    except configparser.Error:
        return None
    if not parser.has_section(section):
        return None
    return any(parser.has_option(section, key) for key in _SELECTION_KEYS)


def config_selects_target(cwd: Path) -> bool:
    """Whether the repo's own mypy config already names the files, packages or modules to check.

    When it does, passing a positional `.` would make mypy ignore that selection entirely and
    walk the whole tree, so files the repository deliberately excluded would be measured and
    baked into `.ebpy/baseline.json` — a ceiling no developer running plain `mypy` could
    reproduce. Reading the same config file mypy would, in mypy's own search order, lets ebpy
    defer to the selection instead of overriding it.
    """
    for name in _CONFIG_FILES:
        path = cwd / name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if name == "pyproject.toml":
            selects = _toml_selects_target(text)
        else:
            # `.mypy.ini` and `mypy.ini` carry the global options under `[mypy]`; `setup.cfg`
            # under `[mypy]` too. mypy stops at the first file with a mypy section, so a file
            # present but without one is skipped rather than treated as an empty selection.
            selects = _ini_selects_target(text, "mypy")
        if selects is not None:
            return selects
    return False


def parse_mypy_output(output: str, cwd: Path) -> AnalysisMeasurement:
    """Turn mypy's text output into cells keyed like Ruff's, under the `mypy:` namespace."""
    cells: CellCounts = {}
    seen_files: set[str] = set()
    for line in output.splitlines():
        if _MYPY_ERROR_PREFIX.match(line) is None:
            continue
        match = _MYPY_ERROR_LINE.match(line)
        if match is None:
            # A code mypy did report but this parser failed to read would silently
            # disappear from the count, which is worse than refusing to measure at all.
            raise MypyInvalidOutputError(f"mypy produced an unparseable error line: {line!r}")
        file = normalize_analyzer_path(match["file"], cwd)
        if PureWindowsPath(file).is_absolute() or PurePosixPath(file).is_absolute():
            # A finding mypy reported for a path outside cwd — a config whose files/packages
            # points at, say, `../shared`. normalize_analyzer_path keeps it absolute, so the
            # cell key would embed this host's directory layout and no other machine could
            # reproduce the ceiling. The kept-absolute path may be rooted in either flavour —
            # a POSIX `/…` on a POSIX host, a drive-qualified `C:/…` on Windows — and only
            # PureWindowsPath recognises a drive root, so both flavours are tested. Refuse
            # rather than write a host-dependent baseline.
            raise MypyInvalidOutputError(
                f"mypy reported a finding outside the repository ({file!r}); a config that checks "
                "paths outside the repository cannot produce a reproducible baseline"
            )
        rule = qualify_rule("mypy", match["code"])
        seen_files.add(file)
        file_cells = cells.setdefault(file, {})
        file_cells[rule] = file_cells.get(rule, 0) + 1
    return AnalysisMeasurement(cells=cells, files_with_findings=len(seen_files))


def _summary_clause(output: str) -> str:
    """The one line of mypy's complaint a human acts on, for the summary reading.

    Which line that is depends on how mypy failed: a rejected argument prints a two-line
    usage banner and puts ``mypy: error: ...`` last, while a bad config file prints its
    complaint alone. Preferring the last error line and falling back to the first covers
    both without parsing either. The whole output still travels as the detail.
    """
    lines = [text for line in output.splitlines() if (text := line.strip())]
    if not lines:
        return ""
    errors = [line for line in lines if "error:" in line]
    return f": {(errors[-1] if errors else lines[0])[:_SUMMARY_LIMIT]}"


def run_mypy_check(cwd: Path) -> AnalysisMeasurement:
    """Today's mypy findings, as cells keyed like Ruff's, raising when none could be measured."""
    argv = find_mypy(cwd)
    if not argv:
        raise MypyNotFoundError(
            "mypy is not installed here (looked in .venv, venv and PATH). Run `ebpy bootstrap` first."
        )
    # A positional target makes mypy ignore the config's own files/packages/modules
    # selection, so it is passed only when the config names no target of its own.
    target = [] if config_selects_target(cwd) else ["."]
    try:
        result = run(
            [
                *argv,
                *target,
                "--no-error-summary",  # drops a localised trailer that is not itself a finding
                "--show-error-codes",  # overrides a repo's own `hide_error_codes = true`
                "--no-pretty",  # keeps one finding on one line, so the parser can line-match it
                "--no-color-output",  # keeps ANSI escapes out of codes and messages
            ],
            cwd,
        )
    except OSError as error:
        raise MypyFailedError(f"mypy could not run: {error}") from error
    # 0 = clean, 1 = errors found; only those two mean mypy actually completed a run. A
    # positive code beyond that is a mypy failure, and a negative one means a signal
    # terminated the process — neither produced output worth parsing, so cells found in
    # it (e.g. a valid-looking `[syntax]` line) are discarded rather than trusted.
    if result.code not in (0, 1):
        headline = f"mypy failed (exit {result.code})"
        output = (result.stderr or result.stdout).strip()
        raise MypyFailedError(
            f"{headline}{_summary_clause(output)}",
            detail=f"{headline}:\n{output}" if output else headline,
        )
    measured = parse_mypy_output(result.stdout, cwd)
    if result.code == 0 and measured.cells:
        raise MypyInvalidOutputError(
            "mypy exited 0 (clean) but its output reported findings; exit code and output disagree"
        )
    if result.code == 1 and not measured.cells:
        # mypy can report a real error that carries no `:line:` location — a non-blocker
        # emitted with line=-1, e.g. `pkg/sub: error: Ancestor package "pkg" ignored` under
        # `follow_imports = error`. The strict parser attributes no cell to such a line, but
        # the exit code and the error text agree that mypy found something, so this is an
        # ordinary failure whose text the user should see, not garbled output to refuse.
        output = result.stdout.strip()
        if "error:" in output:
            headline = "mypy exited 1 with an error carrying no location"
            raise MypyFailedError(
                f"{headline}{_summary_clause(output)}",
                detail=f"{headline}:\n{output}",
            )
        raise MypyInvalidOutputError(
            "mypy exited 1 (errors found) but no error line could be parsed from its output"
        )
    return measured
