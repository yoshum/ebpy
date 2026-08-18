"""Command prefixes shared by package-manager-aware operations."""

from __future__ import annotations

from .models import PackageManager

DEV_INSTALL_PREFIXES: dict[PackageManager, tuple[str, ...]] = {
    "uv": ("uv", "add", "--dev"),
    "poetry": ("poetry", "add", "--group", "dev"),
    "pdm": ("pdm", "add", "-d"),
    "pipenv": ("pipenv", "install", "--dev"),
    "pip": ("pip", "install"),
}

RUN_PREFIXES: dict[PackageManager, tuple[str, ...]] = {
    "uv": ("uv", "run"),
    "poetry": ("poetry", "run"),
    "pdm": ("pdm", "run"),
    "pipenv": ("pipenv", "run"),
}
