"""The mypy config ebpy writes into a repository, as text.

Rendered from constants rather than templated files so the tests can assert on exactly
what a repository receives. Nothing here is ever written over an existing config — the
exceptions in an existing config have reasons that are not in the file.
"""

from __future__ import annotations

MYPY_PYPROJECT_SECTION = "[tool.mypy]\nstrict = true\n"

MYPY_INI_CONTENT = "[mypy]\nstrict = True\n"
