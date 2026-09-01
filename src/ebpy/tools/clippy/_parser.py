"""One `cargo clippy` invocation's stdout into one AnalysisMeasurement.

One invocation, one call. "Exactly one build-finished" is an invariant of a single cargo
run, so concatenating two workspaces' output before parsing would break it — which is why
this function takes the workspace it is parsing rather than a list of them.

Two passes over the messages, not one: `build-script-executed` may arrive after the
diagnostics it explains, so every `out_dir` is collected before any path is classified. The
first pass is the scan below; the second is `_measure`, which runs once the scan is complete.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from ebpy.cell_key import qualify_rule
from ebpy.models import AnalysisMeasurement, CellCounts, UnattributedFinding, UnmeasuredScope

from ._errors import ClippyFailedError, ClippyInvalidOutputError
from ._paths import attribute_path, normalize_out_dir

if TYPE_CHECKING:
    from pathlib import Path

    from ._topology import RustWorkspace

# Observed identical on 1.79, 1.85 and 1.96 — the error prose around it is not. Tested for
# by presence of this one substring, never by matching the note set: 1.85 adds a second note
# ("the item is gated here"), and an equality test would have broken there. If rustc ever
# rewords it, recognition is lost and the behaviour reverts to Failed, which is the safe
# direction: a workspace stops being dropped rather than being dropped wrongly.
_CONFIGURED_OUT = "found an item that was configured out"

_STDERR_TAIL = 20


@dataclass(frozen=True)
class _Candidate:
    """One warning that survived every staged check, before its path was classified."""

    file: str
    line: int
    column: int
    code: str
    message: str


@dataclass
class _Scan:
    """Everything one pass over stdout collected, before any verdict is reached."""

    objects: int = 0
    finished: list[bool] = field(default_factory=list)
    out_dirs: list[str] = field(default_factory=list)
    candidates: list[_Candidate] = field(default_factory=list)
    error_rendered: list[str] = field(default_factory=list)
    any_rendered: list[str] = field(default_factory=list)
    # Errors carrying at least one span, and whether each was explained by a cfg note. Read
    # leniently, and only once failure is certain.
    spanned_errors: list[bool] = field(default_factory=list)


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ClippyInvalidOutputError(detail)


def _positive_int(value: object) -> bool:
    # `isinstance(True, int)` is true, so a bare isinstance check would read `true` as line 1.
    return type(value) is int and value > 0


def _configured_out(message: dict[str, Any]) -> bool:
    """Whether rustc explained this error as a reference to a `cfg`-excluded item.

    Read but never type-checked. This is consulted only after the build is known to have
    failed, so rejecting a malformed value here would downgrade a real `execution-failed`
    into `invalid-output`. An unreadable value falls to False, which means "real failure",
    which means the workspace stays measured — the safe direction, automatically.
    """
    children = message.get("children")
    if not isinstance(children, list):
        return False
    return any(
        isinstance(child, dict) and isinstance(text := child.get("message"), str) and _CONFIGURED_OUT in text
        for child in children
    )


def _read_warning(message: dict[str, Any]) -> _Candidate | None:
    """Apply the staged checks a warning must pass to become a cell, or return None to discard."""
    code = message.get("code")
    _require(code is None or isinstance(code, dict), "clippy reported a message code of an unexpected shape")
    if code is None:
        return None
    spans = message.get("spans")
    # An explicit isinstance/raise rather than `_require`: mypy cannot narrow through a
    # helper, and `spans` is iterated below.
    if not isinstance(spans, list):
        raise ClippyInvalidOutputError("clippy reported spans that are not a list")
    primaries = []
    for span in spans:
        _require(isinstance(span, dict), "clippy reported a span of an unexpected shape")
        primary = span.get("is_primary", False)
        _require(isinstance(primary, bool), "clippy reported a non-boolean is_primary")
        if primary:
            primaries.append(span)
    if not primaries:
        return None
    for span in primaries:
        _require(
            isinstance(span.get("file_name"), str) and bool(span["file_name"]),
            "clippy reported a primary span without a file name",
        )
        _require(
            _positive_int(span.get("line_start")) and _positive_int(span.get("column_start")),
            "clippy reported a primary span without a positive line and column",
        )
    # Checked last, because a message with no primary span is discarded regardless: making a
    # run fail over a value it never reads is the one thing the staged order exists to avoid.
    local = code.get("code")
    _require(
        isinstance(local, str) and bool(local) and "\n" not in local and "\r" not in local,
        "clippy reported a rule code that cannot be part of a cell key",
    )
    chosen = min(primaries, key=itemgetter("file_name", "line_start", "column_start"))
    text = message.get("message")
    # Same reasoning as `spans` above: `text` is passed to `_Candidate.message`, a `str` field.
    if not isinstance(text, str):
        raise ClippyInvalidOutputError("clippy reported a message text that is not a string")
    return _Candidate(
        file=chosen["file_name"],
        line=chosen["line_start"],
        column=chosen["column_start"],
        code=local,
        message=text,
    )


def _read_compiler_message(scan: _Scan, payload: dict[str, Any]) -> None:
    """Read one `compiler-message` object into `scan`, applying staged checks 2 through 10."""
    message = payload.get("message")
    # Explicit isinstance/raise rather than `_require`: mypy cannot narrow through a helper,
    # and `message` is read as a dict, and passed to two other functions, below.
    if not isinstance(message, dict):
        raise ClippyInvalidOutputError("clippy reported a compiler message of an unexpected shape")
    level = message.get("level")
    if not isinstance(level, str):
        raise ClippyInvalidOutputError("clippy reported a message without a string level")
    # Collected before the level is dispatched on, because a failed build's detail needs
    # the error-level text and discarding non-warnings first throws it away.
    if isinstance(rendered := message.get("rendered"), str):
        scan.any_rendered.append(rendered)
        if level == "error":
            scan.error_rendered.append(rendered)
    if level == "error":
        spans = message.get("spans")
        if isinstance(spans, list) and spans:
            scan.spanned_errors.append(_configured_out(message))
        return
    if level != "warning":
        return
    if (candidate := _read_warning(message)) is not None:
        scan.candidates.append(candidate)


def _scan(stdout: str) -> _Scan:
    """Read every interpretable line once, checking only the fields ebpy actually reads."""
    scan = _Scan()
    for line in stdout.splitlines():
        # Cargo's own documented workaround for procedural-macro output on this stream is
        # exactly this test. `lstrip()` would only blur the boundary it draws.
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ClippyInvalidOutputError(f"clippy produced an unreadable JSON line: {error}") from error
        _require(isinstance(payload, dict), "clippy produced a JSON value that is not an object")
        reason = payload.get("reason")
        _require(isinstance(reason, str), "clippy produced a message without a string reason")
        scan.objects += 1

        if reason == "build-finished":
            success = payload.get("success")
            _require(isinstance(success, bool), "clippy reported a non-boolean build-finished success")
            scan.finished.append(success)
        elif reason == "build-script-executed":
            out_dir = payload.get("out_dir")
            _require(isinstance(out_dir, str), "cargo reported a build script without a string out_dir")
            scan.out_dirs.append(normalize_out_dir(out_dir))
        elif reason == "compiler-message":
            _read_compiler_message(scan, payload)
        # Any other reason is unknown, not unreadable, and ebpy ignores it: rustc's own
        # forward-compatibility contract asks exactly this ("future-cargo-message" and the
        # like must not become a rejection just because ebpy has not learned it yet).
    return scan


def _failure_detail(scan: _Scan, stderr: str) -> str:
    """Quote what the compiler said: the first of three rules that produces anything wins.

    `observation._describe` keeps only the first lines of a detail, so a warning must never
    be able to displace a real compile error out of that window. Excluding the transcript is
    how this is solved, not ordering within it: if any error-level `rendered` text exists, it
    is the whole detail, full stop — appending the rest of the transcript after it would let
    a long error list's own tail get truncated away by trailing warnings, which is the same
    failure this rule exists to prevent. Only a build with no error-level message at all falls
    back to every level's `rendered` text; only a build with no `rendered` text anywhere falls
    back to stderr's tail. Never rebuilt from structured fields; that would reimplement
    rustc's own formatting and drift with every rustc version.
    """
    if scan.error_rendered:
        return "\n".join(scan.error_rendered)
    if scan.any_rendered:
        return "\n".join(scan.any_rendered)
    return "\n".join(stderr.splitlines()[-_STDERR_TAIL:])


def _measure(scan: _Scan, workspace: RustWorkspace, repo_root: Path) -> AnalysisMeasurement:
    cells: CellCounts = {}
    unattributed: list[UnattributedFinding] = []
    root = workspace.root.as_posix()
    for candidate in scan.candidates:
        verdict = attribute_path(
            candidate.file, workspace_root=root, repo_root=repo_root, out_dirs=scan.out_dirs
        )
        if verdict.kind == "generated":
            continue
        if verdict.kind == "unattributed":
            # The reported path verbatim, not the prefixed one: a reader has to be able to
            # match this against clippy's own output, and a path ebpy assembled would send
            # them looking for a file that was never named.
            unattributed.append(
                UnattributedFinding(file=candidate.file, line=candidate.line, message=candidate.message)
            )
            continue
        try:
            rule = qualify_rule("clippy", candidate.code)
        except ValueError as error:
            raise ClippyInvalidOutputError(f"clippy reported an unusable rule code: {error}") from error
        file_cells = cells.setdefault(verdict.path, {})
        file_cells[rule] = file_cells.get(rule, 0) + 1
    return AnalysisMeasurement(cells=cells, unattributed=tuple(unattributed))


def parse_clippy_output(
    stdout: str, stderr: str, returncode: int, *, workspace: RustWorkspace, repo_root: Path
) -> AnalysisMeasurement:
    """Turn one invocation's output into a measurement, or say why it is not one.

    The order of the checks below is itself the specification. Unreadable output comes first
    because nothing can be concluded from it — not even from a `success: true` sitting beside
    a broken line: `_scan` reads every line before any verdict below is reached, so a malformed
    line anywhere raises before "no output" or "no build-finished" is ever considered. "No
    output at all" comes before "no completion marker" because cargo dying silently is the
    tool failing, while cargo speaking without finishing is ebpy failing to read it, and those
    deserve different words.

    A build that failed only because it references items this configuration excludes returns
    the workspace as unmeasured rather than raising: it is a range ebpy does not cover, not a
    broken repository.
    """
    scan = _scan(stdout)
    if scan.objects == 0:
        headline = f"cargo clippy produced no output (exit {returncode})"
        tail = "\n".join(stderr.splitlines()[-_STDERR_TAIL:])
        raise ClippyFailedError(headline, detail=f"{headline}:\n{tail}" if tail else headline)
    _require(len(scan.finished) == 1, "clippy did not report exactly one build-finished message")

    # Both are required: the contract guarantees `success` describes the build, and separately
    # that a normal cargo command reports success with exit 0. Neither implies the other.
    if not scan.finished[0] or returncode != 0:
        if scan.spanned_errors and all(scan.spanned_errors):
            return AnalysisMeasurement(
                cells={},
                unmeasured=(UnmeasuredScope(root=workspace.root.as_posix(), packages=workspace.packages),),
            )
        raise ClippyFailedError(
            f"cargo clippy could not build this workspace (exit {returncode})",
            detail=_failure_detail(scan, stderr),
        )
    return _measure(scan, workspace, repo_root)
