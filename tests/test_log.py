"""`ebpy log`: --rule accepts only a namespaced rule ID, and a valid one is recorded."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ebpy.commands.log import run_log
from ebpy.errors import CommandError

if TYPE_CHECKING:
    from pathlib import Path


def test_log_refuses_an_unnamespaced_rule(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match=r"--rule must be a namespaced rule ID, e\.g\. ruff:C901"):
        run_log(tmp_path, "note", "saw this", "C901")


def test_log_records_a_namespaced_rule(tmp_path: Path) -> None:
    """A well-formed namespaced rule is accepted and recorded.

    A refusal test alone would pass if the validator rejected every rule, namespaced or
    not — this pins that a well-formed namespaced rule is accepted and recorded.
    """
    message = run_log(tmp_path, "deferred", "router.py needs splitting", "ruff:C901")

    assert message == "Recorded deferred: router.py needs splitting"
