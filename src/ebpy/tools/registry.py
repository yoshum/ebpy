"""Static registries of ebpy's built-in tool capabilities (analyzers, detectors, provisioners)."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from ebpy.measurement import Measurement

from .gitleaks import GitleaksDetector, GitleaksProvisioner
from .mypy import MypyAnalyzer, MypyDetector, MypyProvisioner
from .pytest import PytestDetector, PytestProvisioner
from .ruff import RuffAnalyzer, RuffDetector, RuffProvisioner
from .ruff_format import RuffFormatDetector, RuffFormatProvisioner
from .vulture import VultureDetector, VultureProvisioner

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from ebpy.decide.provisioner import Provisioner
    from ebpy.measurement import Analyzer
    from ebpy.repo.detect.detector import ToolDetector

# Build via a typed list so mypy can verify Protocol compatibility and infer
# tuple[Analyzer, ...] for ANALYZERS rather than the narrower concrete tuple.
_registry: list[Analyzer] = [RuffAnalyzer(), MypyAnalyzer()]

ANALYZERS: tuple[Analyzer, ...] = tuple(_registry)

ANALYZERS_BY_NAME: Mapping[str, Analyzer] = MappingProxyType({a.name: a for a in ANALYZERS})

# Derived from the registry so the name list cannot drift from the actual set.
ANALYZER_NAMES: tuple[str, ...] = tuple(sorted(ANALYZERS_BY_NAME))

# Build via a typed list so mypy can verify Protocol compatibility and infer
# tuple[ToolDetector[Any], ...] for DETECTORS rather than the narrower concrete tuple.
# Any is required for the type parameter because the registry is heterogeneous:
# most detectors use ToolSetup but MypyDetector uses MypySetup, and S appears
# in both covariant (detect return) and contravariant (gaps/render_row parameter)
# positions, making ToolDetector invariant in S.
#
# Order is the diagnosis display order: it drives both the gap sequence and the report rows,
# which the report renders in this order before appending the repository-level pre-commit and
# agent-rules rows.
_detectors: list[ToolDetector[Any]] = [
    RuffDetector(),
    RuffFormatDetector(),
    MypyDetector(),
    PytestDetector(),
    VultureDetector(),
    GitleaksDetector(),
]

DETECTORS: tuple[ToolDetector[Any], ...] = tuple(_detectors)

DETECTORS_BY_NAME: Mapping[str, ToolDetector[Any]] = MappingProxyType({d.name: d for d in DETECTORS})

# Build via a typed list so mypy can verify Protocol compatibility and infer
# tuple[Provisioner, ...] for PROVISIONERS rather than the narrower concrete tuple.
# Order matches DETECTORS: it is the canonical tool sequence across the whole CLI.
_provisioners: list[Provisioner] = [
    RuffProvisioner(),
    RuffFormatProvisioner(),
    MypyProvisioner(),
    PytestProvisioner(),
    VultureProvisioner(),
    GitleaksProvisioner(),
]

PROVISIONERS: tuple[Provisioner, ...] = tuple(_provisioners)

PROVISIONERS_BY_NAME: Mapping[str, Provisioner] = MappingProxyType({p.name: p for p in PROVISIONERS})


def measure_repository(cwd: Path, scope: tuple[str, ...]) -> Measurement:
    """Measure the analyzers named in ``scope``, retaining partial success as data.

    The registry holds no policy about which analyzers apply to a repository: `scope` arrives
    as a value from the caller that computed it. A name with no runner here is skipped rather
    than raised — that missing key is exactly how `classify(None)` reports "no runner in this
    build", and a KeyError would replace the one message a reader could act on.
    """
    return Measurement(
        analyzers={name: ANALYZERS_BY_NAME[name].measure(cwd) for name in scope if name in ANALYZERS_BY_NAME}
    )
