"""The configs bootstrap writes, as text.

Rendered from constants rather than templated files so the tests can assert on
exactly what a repository receives. Nothing here is ever written over an
existing config — the exceptions in an existing config have reasons that are
not in the file.
"""

from __future__ import annotations

import re

# Each select group covers what the others cannot see, mirroring the layers the approach
# depends on: function size and complexity (C90, PL), bug patterns (F, B, SIM), types
# and readability (UP, N, ARG), and mechanical style Ruff formats away.
_RUFF_SELECT = """\
select = [
  "E",   # pycodestyle errors
  "W",   # pycodestyle warnings
  "F",   # pyflakes — undefined names, unused imports, real bugs
  "B",   # bugbear — mutable defaults, loop variables captured late
  "C90", # mccabe — cognitive complexity
  "I",   # isort — import order, so diffs stop fighting over it
  "N",   # pep8-naming
  "UP",  # pyupgrade — syntax the requires-python already allows
  "SIM", # simplify — collapsible ifs, needless bool gymnastics
  "C4",  # comprehensions
  "ARG", # unused arguments — an argument nobody reads is an API lying
  "PL",  # pylint — too many branches, returns, statements
  "RUF", # ruff-specific
]
"""


def ruff_pyproject_section(target_version: str) -> str:
    """Appended to an existing pyproject.toml that has no [tool.ruff] table."""
    return (
        f'[tool.ruff]\nline-length = 100\ntarget-version = "{target_version}"\n'
        f"\n[tool.ruff.lint]\n{_RUFF_SELECT}"
        "\n[tool.ruff.lint.mccabe]\nmax-complexity = 10\n"
    )


def ruff_toml_content(target_version: str) -> str:
    """A standalone ruff.toml, for a repository with no pyproject.toml to append to."""
    return (
        f'line-length = 100\ntarget-version = "{target_version}"\n'
        f"\n[lint]\n{_RUFF_SELECT}"
        "\n[lint.mccabe]\nmax-complexity = 10\n"
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
"""
