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

# No "pip" row, though DEV_INSTALL_PREFIXES keeps one for the bootstrap plan. Every other manager
# has a runner that resolves the dependency it just installed; pip would leave a bare `ebpy` to PATH,
# which under the documented `uvx --from git+...` bootstrap is the bootstrap copy rather than the
# revision just pinned. `ebpy install` refuses the pip fallback instead of writing skills from it.
RUN_PREFIXES: dict[PackageManager, tuple[str, ...]] = {
    "uv": ("uv", "run"),
    "poetry": ("poetry", "run"),
    "pdm": ("pdm", "run"),
    "pipenv": ("pipenv", "run"),
}
