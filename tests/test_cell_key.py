from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from ebpy.cell_key import (
    analyzer_of,
    is_analyzer_name,
    is_rule_id,
    normalize_analyzer_path,
    qualify_rule,
    split_rule,
)


def test_qualify_and_split_round_trip_every_valid_rule() -> None:
    assert qualify_rule("ruff", "F401") == "ruff:F401"
    assert split_rule("ruff:F401") == ("ruff", "F401")
    assert analyzer_of("mypy:arg-type") == "mypy"


def test_split_rule_keeps_a_colon_inside_the_local_code() -> None:
    """The first colon is the separator, so a local code may contain colons of its own."""
    assert split_rule("mypy:a:b") == ("mypy", "a:b")


@pytest.mark.parametrize("analyzer", ["", "Ruff", "1ruff", "-ruff", "ru ff", "ru:ff"])
def test_qualify_rule_rejects_an_invalid_analyzer_name(analyzer: str) -> None:
    with pytest.raises(ValueError, match="not a valid analyzer name"):
        qualify_rule(analyzer, "F401")


@pytest.mark.parametrize("code", ["", "F4\n01", "F4\r01"])
def test_qualify_rule_rejects_an_empty_or_multiline_local_code(code: str) -> None:
    with pytest.raises(ValueError, match="not a valid local rule code"):
        qualify_rule("ruff", code)


@pytest.mark.parametrize("value", [None, 7, "F401", "", ":F401", "ruff:", "Ruff:F401"])
def test_is_rule_id_is_total_and_rejects_anything_unnamespaced(value: object) -> None:
    assert is_rule_id(value) is False


def test_is_analyzer_name_accepts_the_two_shipped_analyzers() -> None:
    assert is_analyzer_name("ruff") and is_analyzer_name("mypy")


def test_normalize_keeps_a_relative_path_relative(tmp_path: Path) -> None:
    assert normalize_analyzer_path("src/a.py", tmp_path) == "src/a.py"


def test_normalize_converts_backslashes_to_posix_separators(tmp_path: Path) -> None:
    assert normalize_analyzer_path("src\\pkg\\a.py", tmp_path) == "src/pkg/a.py"


def test_normalize_makes_an_absolute_path_under_cwd_repository_relative(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "a.py"
    target.write_text("", encoding="utf-8")
    assert normalize_analyzer_path(str(target), tmp_path) == "src/a.py"


def test_normalize_leaves_an_absolute_path_outside_cwd_absolute(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere" / "a.py"
    result = normalize_analyzer_path(str(outside), tmp_path)
    # The result stays absolute rather than being relativized. Asserted in both flavours so
    # the claim holds on a POSIX host (`/...`) and a Windows host (`C:/...`) alike.
    assert PurePosixPath(result).is_absolute() or PureWindowsPath(result).is_absolute()


def test_normalize_reads_a_windows_drive_path_without_the_host_being_windows(tmp_path: Path) -> None:
    """A POSIX test host must still classify `C:\\work\\src\\a.py` the way Windows would."""
    assert PureWindowsPath("C:\\work\\src\\a.py").is_absolute()
    assert normalize_analyzer_path("C:\\work\\src\\a.py", tmp_path) == "C:/work/src/a.py"


def test_split_rule_rejects_a_string_with_no_colon() -> None:
    """A rule id without a namespace separator is exactly the shape `is_rule_id` refuses too."""
    with pytest.raises(ValueError, match="not a namespaced rule id"):
        split_rule("F401")


def test_analyzer_of_rejects_an_invalid_rule_id() -> None:
    with pytest.raises(ValueError, match="not a namespaced rule id"):
        analyzer_of("Ruff:F401")


def test_qualify_rule_accepts_a_local_code_containing_a_colon() -> None:
    """`split_rule` must recover the same pair `qualify_rule` was given, colon and all."""
    assert split_rule(qualify_rule("mypy", "a:b")) == ("mypy", "a:b")


@pytest.mark.parametrize("analyzer", ["", "Ruff", "1ruff", "-ruff", "ru ff", "ru:ff"])
def test_is_analyzer_name_rejects_the_same_names_qualify_rule_rejects(analyzer: str) -> None:
    assert is_analyzer_name(analyzer) is False
