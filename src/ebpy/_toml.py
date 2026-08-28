"""The TOML reader, chosen once for the whole package.

``tomllib`` only entered the standard library in 3.11. On 3.10 its upstream,
``tomli``, stands in for it — same API, same exception — so that every caller
can read TOML without repeating the version check.
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from tomllib import TOMLDecodeError, loads
else:
    from tomli import TOMLDecodeError, loads

__all__ = ["TOMLDecodeError", "loads"]
