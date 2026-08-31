"""Whether the ranges this run could not measure narrow the frozen contract.

The runner reports one fact — "this range was not measured". Whether that fact is a
regression needs the ceiling, which the measurement seam deliberately does not know
(`docs/measurement-seam.md`: *The seam owns measured facts. It does not own ceilings, gate
policy or persistence.*). That judgment lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ebpy.measurement import Measured, classify
from ebpy.store.baseline import cells_for

if TYPE_CHECKING:
    from ebpy.measurement import Measurement
    from ebpy.models import CellCounts, State, UnmeasuredScope

# Exported: report.py must agree with this module on which analyzer's regressed backlog to
# carry forward rather than let a missing measurement read as drained debt.
UNMEASURED_ANALYZER = "clippy"
_NAMED_CELLS = 5


@dataclass(frozen=True)
class UnmeasuredVerdict:
    """What this run did not measure, and whether that is a narrowing of the contract."""

    scopes: tuple[UnmeasuredScope, ...]
    packages: tuple[str, ...]
    # Whether clippy produced a complete measurement this run. Only then may the contract's
    # recorded set be replaced — an empty set from a run that never happened would record
    # "nothing is excluded" as the outcome of not looking.
    measured: bool
    regressed: bool
    # Baseline cells inside the newly dropped packages, for the message. Approximate on
    # purpose: the judgment above is set containment and must be sound; naming may not be.
    lost_cells: tuple[str, ...]


def unmeasured_verdict(measurement: Measurement, previous: State, baseline: CellCounts) -> UnmeasuredVerdict:
    """Decide whether this run's unmeasured ranges leave the contract's coverage."""
    observation = measurement.analyzers.get(UNMEASURED_ANALYZER)
    measured = isinstance(observation, Measured) and classify(observation) == "complete"
    scopes = observation.value.unmeasured if isinstance(observation, Measured) else ()
    packages = tuple(sorted({package for scope in scopes for package in scope.packages}))
    covered = set(previous.unmeasured_packages)
    newly = sorted(set(packages) - covered)
    # Kept: outside the contract clippy holds no ceiling, and claiming a regression there
    # would gate on a ceiling that does not exist — which is the invariant
    # `test_a_non_contract_analyzer_is_named_but_never_gates` already pins. Without it, a
    # Python repository's check fails because of a Rust fuzz workspace sitting beside it.
    regressed = UNMEASURED_ANALYZER in previous.frozen_analyzers and bool(newly)
    return UnmeasuredVerdict(
        scopes=scopes,
        packages=packages,
        measured=measured,
        regressed=regressed,
        lost_cells=_cells_under(baseline, newly) if regressed else (),
    )


def _cells_under(baseline: CellCounts, packages: list[str]) -> tuple[str, ...]:
    prefixes = tuple(f"{package}/" for package in packages if package != ".")
    named = [
        f"{file}:{rule}"
        for file, rules in sorted(cells_for(baseline, UNMEASURED_ANALYZER).items())
        for rule in sorted(rules)
        if not prefixes or file.startswith(prefixes)
    ]
    return tuple(named[:_NAMED_CELLS])


def next_unmeasured_packages(previous: State, verdict: UnmeasuredVerdict) -> tuple[str, ...]:
    """Choose the set to persist: this run's, but only from a run that actually measured and passed."""
    if verdict.measured and not verdict.regressed:
        return verdict.packages
    return previous.unmeasured_packages


def unmeasured_notice(verdict: UnmeasuredVerdict) -> list[str]:
    """Say out loud which ranges hold no ceiling, and what that costs.

    The last sentence is the point: a range ebpy never measured is not gated either. Its
    ceiling cannot fall, but it cannot rise, and a reader has to be able to find that out
    somewhere other than this file.
    """
    if not verdict.scopes:
        return []
    count = len(verdict.scopes)
    return [
        f"{count} workspace(s) not measured in this configuration:",
        *(
            f"  {scope.root} does not compile in the configuration ebpy measures."
            " It references items hidden behind a `cfg`. ebpy holds no ceiling for it,"
            " and new violations there are not gated."
            for scope in verdict.scopes
        ),
    ]


def regression_refusal(verdict: UnmeasuredVerdict) -> str:
    """Name what stopped being measured, and offer both exits rather than choosing one.

    Packages are named directly, not only through `lost_cells`: a workspace with no cells at
    all (a clean one, or one that never held a violation) would otherwise refuse with nothing
    to point at beyond its root.
    """
    return "\n".join(
        [
            *(
                f"{scope.root} no longer compiles in the configuration ebpy measures."
                for scope in verdict.scopes
            ),
            f"  packages: {', '.join(verdict.packages)}",
            *(f"  {cell}" for cell in verdict.lost_cells),
            "Fix the `cfg` so these compile again, or run `ebpy freeze --force`",
            "to accept the narrower contract deliberately.",
        ]
    )
