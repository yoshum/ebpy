from __future__ import annotations

import json
from pathlib import Path

from ebpy.mypy_runner import count_errors
from ebpy.ruff_runner import parse_ruff_json


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
    assert result.cells == {"src/a.py": {"E501": 2}, "src/b.py": {"F401": 1}}
    assert result.files_with_findings == 2


def test_paths_are_reported_relative_and_posix(tmp_path: Path) -> None:
    result = parse_ruff_json(json.dumps([diagnostic(str(tmp_path / "pkg" / "mod.py"), "E501")]), tmp_path)
    assert list(result.cells) == ["pkg/mod.py"]


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


def test_mypy_errors_are_counted_from_the_lines_not_the_summary() -> None:
    output = (
        "src/a.py:12: error: Incompatible return value type\n"
        "src/a.py:19:4: error: Missing type parameters\n"
        "src/b.py:3: note: See https://example.invalid\n"
    )
    assert count_errors(output) == 2


def test_clean_mypy_output_counts_zero() -> None:
    assert count_errors("") == 0
