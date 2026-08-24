from __future__ import annotations

import json
from pathlib import Path

import pytest

from ebpy.cell_key import normalize_analyzer_path
from ebpy.tools.mypy import _runner as mypy_runner
from ebpy.tools.mypy._runner import (
    MypyFailedError,
    MypyInvalidOutputError,
    parse_mypy_output,
    run_mypy_check,
)
from ebpy.tools.ruff._runner import RuffInvalidOutputError, parse_ruff_json
from ebpy.util import ExecResult


def diagnostic(filename: str, code: str | None, row: int = 1, message: str = "boom") -> dict[str, object]:
    return {
        "filename": filename,
        "code": code,
        "message": message,
        "location": {"row": row, "column": 1},
    }


def test_violations_are_counted_per_file_per_rule(tmp_path: Path) -> None:
    payload = json.dumps(
        [
            diagnostic(str(tmp_path / "src" / "a.py"), "E501"),
            diagnostic(str(tmp_path / "src" / "a.py"), "E501"),
            diagnostic(str(tmp_path / "src" / "b.py"), "F401"),
        ]
    )
    result = parse_ruff_json(payload, tmp_path)
    assert result.cells == {"src/a.py": {"ruff:E501": 2}, "src/b.py": {"ruff:F401": 1}}
    assert result.files_with_findings == 2


def test_ruff_findings_are_namespaced_under_ruff(tmp_path: Path) -> None:
    result = parse_ruff_json(json.dumps([diagnostic(str(tmp_path / "a.py"), "F401")]), tmp_path)
    assert result.cells == {"a.py": {"ruff:F401": 1}}


def test_paths_are_reported_relative_and_posix(tmp_path: Path) -> None:
    result = parse_ruff_json(json.dumps([diagnostic(str(tmp_path / "pkg" / "mod.py"), "E501")]), tmp_path)
    assert list(result.cells) == ["pkg/mod.py"]


def test_ruff_delegates_path_normalization_to_cell_key(tmp_path: Path) -> None:
    """The runner calls cell_key.normalize_analyzer_path rather than reimplementing it, so a
    later change to that shared normalization is felt here too instead of silently diverging."""
    raw = str(tmp_path / "pkg" / "mod.py")
    result = parse_ruff_json(json.dumps([diagnostic(raw, "E501")]), tmp_path)
    assert list(result.cells) == [normalize_analyzer_path(raw, tmp_path)]


def test_a_syntax_error_is_not_a_rule_the_baseline_can_grandfather(tmp_path: Path) -> None:
    # Ruff reports these with code "invalid-syntax". A file that does not parse is
    # invisible to every rule, so recording a count for it would be a lie.
    payload = json.dumps(
        [diagnostic(str(tmp_path / "broken.py"), "invalid-syntax", message="unexpected EOF")]
    )
    result = parse_ruff_json(payload, tmp_path)
    assert result.cells == {}
    assert result.unattributed[0].file == "broken.py"
    assert result.unattributed[0].message == "unexpected EOF"


def test_a_diagnostic_with_no_code_is_treated_the_same_way(tmp_path: Path) -> None:
    result = parse_ruff_json(json.dumps([diagnostic(str(tmp_path / "a.py"), None)]), tmp_path)
    assert result.cells == {}
    assert len(result.unattributed) == 1


def test_a_clean_repository_parses_to_nothing(tmp_path: Path) -> None:
    result = parse_ruff_json("[]", tmp_path)
    assert result.cells == {}
    assert result.files_with_findings == 0


def test_an_invalid_ruff_diagnostic_is_not_reported_as_clean(tmp_path: Path) -> None:
    with pytest.raises(RuffInvalidOutputError, match="index 0"):
        parse_ruff_json("[123]", tmp_path)


def fatal_mypy(
    monkeypatch: pytest.MonkeyPatch,
    stderr: str,
    stdout: str = "",
    code: int = 2,
) -> None:
    monkeypatch.setattr(mypy_runner, "find_mypy", lambda _cwd: ["mypy"])
    monkeypatch.setattr(
        mypy_runner,
        "run",
        lambda _argv, _cwd: ExecResult(code=code, stdout=stdout, stderr=stderr),
    )


def test_mypy_argv_fixes_codes_pretty_colour_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        captured.append(argv)
        return ExecResult(code=0, stdout="", stderr="")

    monkeypatch.setattr(mypy_runner, "find_mypy", lambda _cwd: ["mypy"])
    monkeypatch.setattr(mypy_runner, "run", fake_run)

    run_mypy_check(tmp_path)

    assert captured == [
        ["mypy", ".", "--no-error-summary", "--show-error-codes", "--no-pretty", "--no-color-output"]
    ]


def _capture_mypy_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    captured: list[list[str]] = []

    def fake_run(argv: list[str], _cwd: Path) -> ExecResult:
        captured.append(argv)
        return ExecResult(code=0, stdout="", stderr="")

    monkeypatch.setattr(mypy_runner, "find_mypy", lambda _cwd: ["mypy"])
    monkeypatch.setattr(mypy_runner, "run", fake_run)
    run_mypy_check(tmp_path)
    return captured


def test_mypy_config_naming_files_suppresses_the_positional_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `[tool.mypy] files` selection is honoured, not overridden by a positional `.`.

    A positional argument makes mypy ignore its config's files/packages/modules, so a repo
    that deliberately narrowed its checked set would have the excluded files measured and
    baked into the baseline. Deferring to the config keeps the ceiling reproducible.
    """
    (tmp_path / "pyproject.toml").write_text('[tool.mypy]\nfiles = ["src"]\n', encoding="utf-8")
    captured = _capture_mypy_argv(tmp_path, monkeypatch)
    assert captured == [
        ["mypy", "--no-error-summary", "--show-error-codes", "--no-pretty", "--no-color-output"]
    ]


def test_mypy_config_without_a_target_still_passes_the_positional_dot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mypy config that names no files/packages/modules leaves the `.` in place."""
    (tmp_path / "pyproject.toml").write_text("[tool.mypy]\nstrict = true\n", encoding="utf-8")
    captured = _capture_mypy_argv(tmp_path, monkeypatch)
    assert captured == [
        ["mypy", ".", "--no-error-summary", "--show-error-codes", "--no-pretty", "--no-color-output"]
    ]


def test_mypy_ini_naming_modules_suppresses_the_positional_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The selection may live in mypy.ini's `[mypy]` section, not only in pyproject."""
    (tmp_path / "mypy.ini").write_text("[mypy]\nmodules = app\n", encoding="utf-8")
    captured = _capture_mypy_argv(tmp_path, monkeypatch)
    assert captured == [
        ["mypy", "--no-error-summary", "--show-error-codes", "--no-pretty", "--no-color-output"]
    ]


def test_mypy_ini_takes_precedence_over_a_later_pyproject_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mypy stops at the first config file it finds; a bare mypy.ini wins over pyproject.

    With a `[mypy]` mypy.ini that names no target, mypy never reads pyproject.toml — so its
    `files` there does not apply and the positional `.` must remain.
    """
    (tmp_path / "mypy.ini").write_text("[mypy]\nstrict = True\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[tool.mypy]\nfiles = ["src"]\n', encoding="utf-8")
    captured = _capture_mypy_argv(tmp_path, monkeypatch)
    assert captured == [
        ["mypy", ".", "--no-error-summary", "--show-error-codes", "--no-pretty", "--no-color-output"]
    ]


def test_a_finding_outside_the_repository_is_refused_as_unreproducible(tmp_path: Path) -> None:
    """A config checking `../shared` yields host-absolute paths no other machine reproduces."""
    outside = (tmp_path.parent / "shared" / "mod.py").as_posix()
    output = f"{outside}:3: error: Incompatible types  [assignment]\n"
    with pytest.raises(MypyInvalidOutputError, match="outside the repository"):
        parse_mypy_output(output, tmp_path)


def test_a_fatal_mypy_carries_its_reason_on_the_failure_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The measurement seam keeps one line, so the reason has to survive on it."""
    fatal_mypy(monkeypatch, "mypy.ini: [mypy]: Unrecognized option: bogus\n")

    with pytest.raises(MypyFailedError) as caught:
        run_mypy_check(tmp_path)

    assert caught.value.summary == "mypy failed (exit 2): mypy.ini: [mypy]: Unrecognized option: bogus"
    assert caught.value.detail == "mypy failed (exit 2):\nmypy.ini: [mypy]: Unrecognized option: bogus"


def test_a_usage_banner_does_not_crowd_out_the_error_it_precedes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected argument prints the banner first and the reason last."""
    fatal_mypy(
        monkeypatch,
        "usage: mypy [-h] [-v] [-V] [more options; see below]\n"
        "            [-m MODULE] [-p PACKAGE] [files ...]\n"
        "mypy: error: Mypy no longer supports checking Python 2 code.\n",
    )

    with pytest.raises(MypyFailedError) as caught:
        run_mypy_check(tmp_path)

    # The summary skips the banner for the line a human acts on; the detail keeps both,
    # because a reader with room for every line should not be handed the shorter reading.
    assert caught.value.summary == (
        "mypy failed (exit 2): mypy: error: Mypy no longer supports checking Python 2 code."
    )
    assert caught.value.detail.splitlines() == [
        "mypy failed (exit 2):",
        "usage: mypy [-h] [-v] [-V] [more options; see below]",
        "            [-m MODULE] [-p PACKAGE] [files ...]",
        "mypy: error: Mypy no longer supports checking Python 2 code.",
    ]


def test_a_fatal_mypy_falls_back_to_stdout_when_stderr_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fatal_mypy(monkeypatch, "", stdout="\n  cannot find implementation for module 'x'\n")

    with pytest.raises(MypyFailedError, match="cannot find implementation"):
        run_mypy_check(tmp_path)


def test_a_fatal_mypy_without_output_claims_no_reason_it_does_not_have(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fatal_mypy(monkeypatch, "")

    with pytest.raises(MypyFailedError, match=r"^mypy failed \(exit 2\)$"):
        run_mypy_check(tmp_path)


def test_mypy_signal_exit_is_a_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fatal_mypy(monkeypatch, "Killed", code=-9)

    with pytest.raises(MypyFailedError, match=r"exit -9"):
        run_mypy_check(tmp_path)


def test_an_exit_code_that_is_neither_clean_nor_errors_found_is_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only 0 (clean) and 1 (errors found) mean mypy completed a run; any other code fails.

    Codes 2 and negative signals have their own branches; this pins the general rule for an
    otherwise-undocumented code such as 3, which carries no measurement to keep.
    """
    fatal_mypy(monkeypatch, "boom", code=3)

    with pytest.raises(MypyFailedError, match=r"exit 3"):
        run_mypy_check(tmp_path)


def test_mypy_exit_zero_with_an_error_line_is_invalid_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 0 promises no errors; an error line in the output contradicts that promise."""
    fatal_mypy(monkeypatch, "", stdout="src/a.py:7: error: boom  [arg-type]\n", code=0)

    with pytest.raises(MypyInvalidOutputError):
        run_mypy_check(tmp_path)


def test_mypy_exit_one_with_no_parsed_error_is_invalid_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 1 promises at least one error; parsing none from the output is a contract violation."""
    fatal_mypy(monkeypatch, "", stdout="", code=1)

    with pytest.raises(MypyInvalidOutputError):
        run_mypy_check(tmp_path)


def test_mypy_exit_one_with_an_unlocated_error_line_surfaces_the_real_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mypy can exit 1 with an error that carries no `:line:` location (a non-blocker
    emitted with line=-1, e.g. under `follow_imports = error`). The parser attributes no
    cell to it, but it is a real error, not invalid output — so it must reach the user as
    an ordinary MypyFailedError carrying the text, not be mistaken for garbled output."""
    error_line = 'pkg/sub/mod.py: error: Ancestor package "pkg.sub" ignored  [misc]'
    fatal_mypy(monkeypatch, "", stdout=f"{error_line}\n", code=1)

    with pytest.raises(MypyFailedError) as caught:
        run_mypy_check(tmp_path)

    assert not isinstance(caught.value, MypyInvalidOutputError)
    assert error_line in caught.value.detail
    assert error_line in caught.value.summary


def test_mypy_exit_two_from_a_syntax_error_is_a_measurement_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file that does not parse makes mypy exit 2 while printing `[syntax]` error lines.
    Like Ruff's unparseable files, these stay measured-but-unattributed rather than sinking
    the whole run into a failure that would misdirect the user to fix a configuration error."""
    fatal_mypy(monkeypatch, "", stdout="src/a.py:7: error: invalid syntax  [syntax]\n", code=2)

    measured = run_mypy_check(tmp_path)

    assert measured.cells == {}
    assert len(measured.unattributed) == 1
    assert measured.unattributed[0].file == "src/a.py"
    assert measured.unattributed[0].line == 7
    assert measured.unattributed[0].message == "invalid syntax"


def test_mypy_exit_two_with_no_syntax_lines_stays_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A config or usage error exits 2 without any `[syntax]` line, so there is nothing to
    measure and the run must still be reported as a failure."""
    fatal_mypy(monkeypatch, "mypy.ini: [mypy]: Unrecognized option: bogus\n")

    with pytest.raises(MypyFailedError):
        run_mypy_check(tmp_path)


def test_mypy_exit_two_mixing_a_real_finding_with_a_syntax_error_is_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If exit 2 carries a cell-bearing error alongside a syntax error, mypy did not complete a
    trustworthy run: the cells cannot be trusted as a full measurement, so the run fails closed."""
    fatal_mypy(
        monkeypatch,
        "",
        stdout="src/a.py:7: error: invalid syntax  [syntax]\nsrc/b.py:3: error: boom  [arg-type]\n",
        code=2,
    )

    with pytest.raises(MypyFailedError):
        run_mypy_check(tmp_path)


def test_mypy_parser_reads_line_column_and_end_position_forms(tmp_path: Path) -> None:
    output = "\n".join(
        [
            "src/a.py:7: error: Incompatible return value type  [return-value]",
            "src/a.py:19:4: error: Missing type parameters  [type-arg]",
            "src/a.py:19:4:19:12: error: Incompatible types  [assignment]",
        ]
    )
    measurement = parse_mypy_output(output, tmp_path)
    assert measurement.cells == {
        "src/a.py": {"mypy:return-value": 1, "mypy:type-arg": 1, "mypy:assignment": 1}
    }
    assert measurement.files_with_findings == 1


def test_mypy_parser_keeps_a_colon_that_belongs_to_the_filename(tmp_path: Path) -> None:
    """Backtracking past a false colon keeps a colon-bearing relative name in the cell key.

    The location regex is non-greedy, so a colon inside the filename is not mistaken for the
    `:line:` separator; a repository-relative name carrying colons survives intact.
    """
    output = "weird:12:3.py:7: error: Incompatible argument  [arg-type]"
    measurement = parse_mypy_output(output, tmp_path)
    assert set(measurement.cells) == {"weird:12:3.py"}


def test_mypy_parser_refuses_a_drive_qualified_path_from_outside_the_repo(tmp_path: Path) -> None:
    """A drive-rooted absolute path is unreproducible, so it is refused rather than kept.

    Backtracking past the drive colon still identifies `C:/work/src/a.py` as the filename
    rather than letting `C:` become it, but a drive-qualified path cannot be made
    repository-relative on any host, so the measurement is refused rather than baked into a
    host-dependent baseline. `PurePosixPath` does not recognise a drive root as absolute, so
    this is exactly the case the earlier POSIX-only guard let slip through on Windows.
    """
    output = "C:\\work\\src\\a.py:7:2: error: Incompatible argument  [arg-type]"
    with pytest.raises(MypyInvalidOutputError, match="outside the repository"):
        parse_mypy_output(output, tmp_path)


def test_mypy_parser_aggregates_repeats_of_one_code_in_one_file(tmp_path: Path) -> None:
    output = "\n".join(
        [
            "src/a.py:7: error: one  [arg-type]",
            "src/a.py:9: error: two  [arg-type]",
        ]
    )
    assert parse_mypy_output(output, tmp_path).cells == {"src/a.py": {"mypy:arg-type": 2}}


def test_mypy_parser_ignores_notes_and_blank_lines(tmp_path: Path) -> None:
    output = "\n".join(
        [
            "src/a.py:7: error: boom  [arg-type]",
            "",
            'src/a.py:7: note: Revealed type is "builtins.str"',
        ]
    )
    measurement = parse_mypy_output(output, tmp_path)
    assert measurement.cells == {"src/a.py": {"mypy:arg-type": 1}}


def test_mypy_parser_takes_the_trailing_code_when_the_message_has_brackets(tmp_path: Path) -> None:
    output = 'src/a.py:7: error: Argument has type "list[int]" [x]  [arg-type]'
    assert parse_mypy_output(output, tmp_path).cells == {"src/a.py": {"mypy:arg-type": 1}}


def test_mypy_parser_ignores_a_note_whose_message_body_contains_error_prefix(tmp_path: Path) -> None:
    """A note is not an error, even when its own text spells one out. Only a diagnostic
    whose category directly after the location is `error:` counts, so a note quoting an
    expected type of `error: T` must not refuse the whole measurement."""
    output = "\n".join(
        [
            "src/a.py:7: error: boom  [arg-type]",
            "src/a.py:7: note: Expected type: error: T  [misc]",
        ]
    )
    assert parse_mypy_output(output, tmp_path).cells == {"src/a.py": {"mypy:arg-type": 1}}


def test_mypy_parser_refuses_an_error_line_with_no_code(tmp_path: Path) -> None:
    """A dropped code would silently become zero findings, which is the failure to avoid."""
    with pytest.raises(MypyInvalidOutputError):
        parse_mypy_output("src/a.py:7: error: Incompatible return value type", tmp_path)


def test_mypy_parser_treats_a_syntax_error_as_unattributed_not_a_cell(tmp_path: Path) -> None:
    """A file that does not parse is invisible to every type rule, so mypy's `[syntax]` error
    is recorded as unattributed rather than as a cell the baseline could grandfather — the same
    treatment Ruff's `invalid-syntax` gets."""
    measurement = parse_mypy_output("src/a.py:2: error: invalid syntax  [syntax]", tmp_path)
    assert measurement.cells == {}
    assert len(measurement.unattributed) == 1
    assert measurement.unattributed[0].file == "src/a.py"
    assert measurement.unattributed[0].line == 2
    assert measurement.unattributed[0].message == "invalid syntax"
    assert measurement.files_with_findings == 1


def test_mypy_parser_returns_nothing_for_clean_output(tmp_path: Path) -> None:
    measurement = parse_mypy_output("", tmp_path)
    assert measurement.cells == {} and measurement.files_with_findings == 0
