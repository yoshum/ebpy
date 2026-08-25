"""The repository-level files bootstrap writes, as text.

Rendered from constants rather than templated files so the tests can assert on exactly
what a repository receives. Nothing here belongs to a single tool — a tool's own
generated config lives with that tool under ``tools/``. Nothing here is ever written
over an existing file either: the exceptions in one have reasons that are not in it.
"""

from __future__ import annotations

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
