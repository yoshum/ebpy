"""The configs bootstrap writes, as text.

Rendered from constants rather than templated files so the tests can assert on
exactly what a repository receives. Nothing here is ever written over an
existing config — the exceptions in an existing config have reasons that are
not in the file.
"""

from __future__ import annotations

import re

# Each select group covers what the others cannot see, mirroring the layers the approach
# depends on: function size and complexity (C90, PL), bug patterns (F, B, SIM, PIE),
# performance and modern idioms (PERF, FURB, C4, UP), types and interfaces (ANN, TC, N,
# ARG, A), documentation (D), test hygiene (PT), and mechanical style Ruff formats away.
_RUFF_SELECT = """\
select = [
  "E",     # pycodestyle errors
  "W",     # pycodestyle warnings
  "F",     # pyflakes — undefined names, unused imports, real bugs
  "B",     # bugbear — mutable defaults, loop variables captured late
  "PL",    # pylint — too many branches, returns, statements
  "C90",   # mccabe — cognitive complexity
  "I",     # isort — import order, so diffs stop fighting over it
  "N",     # pep8-naming
  "UP",    # pyupgrade — syntax the requires-python already allows
  "SIM",   # simplify — collapsible ifs, needless bool gymnastics
  "PERF",  # performance anti-patterns
  "FURB",  # refurbishing and modernizing Python codebases
  "C4",    # comprehensions
  "ARG",   # unused arguments — an argument nobody reads is an API lying
  "A",     # builtin shadowing
  "ANN",   # annotations — function annotations
  "TC",    # type-checking — force proper use of TYPE_CHECKING blocks
  "D",     # pydocstyle — missing or malformed docstrings
  "PT",    # pytest
  "RUF",   # ruff-specific
  "PIE",   # misc
]
"""

# Every ignore here resolves a rule that fights the formatter or another selected rule,
# never a rule we are softening: W191/E111/E114/E117 are the indentation checks Ruff's
# own formatter owns, and D203/D206/D300/D213 are the docstring rules that contradict
# D211, the formatter, D301, and D212 respectively.
_RUFF_IGNORE = """\
ignore = [
  "W191",
  "E111",
  "E114",
  "E117",
  "D203",
  "D206",
  "D300",
  "D213",
]
"""

_MAX_COMPLEXITY = 10
_LINE_LENGTH = 100


def ruff_pyproject_section(target_version: str) -> str:
    """Appended to an existing pyproject.toml that has no [tool.ruff] table."""
    return (
        f'[tool.ruff]\nline-length = {_LINE_LENGTH}\ntarget-version = "{target_version}"\n'
        f"\n[tool.ruff.lint]\n{_RUFF_SELECT}\n{_RUFF_IGNORE}"
        f"\n[tool.ruff.lint.mccabe]\nmax-complexity = {_MAX_COMPLEXITY}\n"
    )


def ruff_toml_content(target_version: str) -> str:
    """A standalone ruff.toml, for a repository with no pyproject.toml to append to."""
    return (
        f'line-length = {_LINE_LENGTH}\ntarget-version = "{target_version}"\n'
        f"\n[lint]\n{_RUFF_SELECT}\n{_RUFF_IGNORE}"
        f"\n[lint.mccabe]\nmax-complexity = {_MAX_COMPLEXITY}\n"
    )


MYPY_PYPROJECT_SECTION = "[tool.mypy]\nstrict = true\n"

MYPY_INI_CONTENT = "[mypy]\nstrict = True\n"


def python_version_from_requires(requires: str | None, default: str = "py311") -> str:
    """``requires-python = ">=3.11"`` -> ``py311``, so the generated Ruff config allows
    exactly the syntax the package already promises."""
    if not requires:
        return default
    match = re.search(r"3\.(\d+)", requires)
    return f"py3{match.group(1)}" if match else default


GITATTRIBUTES_CONTENT = "* text=auto eol=lf\n"

# Pinning without an updater is how a repository ends up frozen on a version with a
# known hole, so the actions ebpy pins to SHAs get an updater in the same breath. They
# are grouped into one pull request rather than one per action, because the point is a
# diff somebody reads, not a queue somebody rubber-stamps.
DEPENDABOT_CONTENT = """\
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      actions:
        patterns: ["*"]
"""
