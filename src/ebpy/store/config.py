""".ebpy/config.json: which analyzers a monitored repo declares for ratcheting.

Stored under .ebpy/ rather than pyproject.toml so non-Python repositories (which have
no pyproject) can also be monitored. Reading and validation live here; nothing outside
store/ touches the file. Other modules receive EbpyConfig values only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ebpy.errors import CommandError
from ebpy.tools import ANALYZER_NAMES

if TYPE_CHECKING:
    from pathlib import Path

CONFIG_FILE = ".ebpy/config.json"
CONFIG_VERSION = 1


@dataclass(frozen=True)
class EbpyConfig:
    """The analyzer set a monitored repository has declared for ratcheting."""

    analyzers: tuple[str, ...]


def config_path(cwd: Path) -> Path:
    """Return the absolute path to the config file under ``cwd``."""
    return cwd / CONFIG_FILE


def read_config(cwd: Path) -> EbpyConfig | None:
    """Return the declared analyzer set, or None if no config file exists.

    None means intent is unstated; an explicit empty analyzers list is an error
    rather than a silent no-op, because absent and zero are different.
    """
    path = config_path(cwd)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CommandError(f"{CONFIG_FILE} is unreadable: {error}") from error

    if not isinstance(raw, dict) or raw.get("version") != CONFIG_VERSION:
        raise CommandError(f"{CONFIG_FILE}: unsupported version (expected {CONFIG_VERSION}).")

    analyzers = raw.get("analyzers")
    if not isinstance(analyzers, list) or not all(isinstance(a, str) for a in analyzers):
        raise CommandError(f"{CONFIG_FILE}: 'analyzers' must be a list of strings.")

    if not analyzers:
        raise CommandError(f"{CONFIG_FILE}: 'analyzers' must name at least one analyzer.")

    unknown = sorted(set(analyzers) - set(ANALYZER_NAMES))
    if unknown:
        raise CommandError(f"{CONFIG_FILE}: unknown analyzer(s): {', '.join(unknown)}.")

    return EbpyConfig(analyzers=tuple(sorted(set(analyzers))))
