"""Which analyzers this run measures, and what to say when the authorities disagree.

Three authorities have a claim on the set: `.ebpy/config.json` (what the repository declared),
language detection (what the repository contains), and the frozen roster (what the ceiling
already covers). Carrying them as three bare arguments is how a caller forgets one; carrying
them as one frozen value makes the reconciliation a method and the omission impossible.

`registered_analyzers` is not a fourth authority. It is this build's `ANALYZERS`, and it is
here for one job: keeping a contract analyzer this build has no runner for out of the
mismatch set, so it still reaches `classify(None)` and its one actionable message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ebpy.tools import ANALYZERS

if TYPE_CHECKING:
    from ebpy.models import State
    from ebpy.repo.detect.language import RepoLanguages
    from ebpy.store.config import EbpyConfig


@dataclass(frozen=True)
class ScopeDecision:
    """What three authorities say about the analyzer set, plus what this build can measure.

    All four are sets of **analyzer names**, never of languages. Sets and not tuples: the
    rules below are equality and containment, and comparing tuples would call the same set a
    mismatch because the projection comes out in registry order while `frozen_analyzers`
    comes out sorted. The one place a tuple appears is on the way out, where it is sorted.
    """

    declared: frozenset[str] | None
    detected_analyzers: frozenset[str]
    frozen: frozenset[str]
    registered_analyzers: frozenset[str]

    @property
    def to_measure(self) -> tuple[str, ...]:
        """The set this run actually measures: the declaration if there is one, else detection."""
        source = self.declared if self.declared is not None else self.detected_analyzers
        return tuple(sorted(source))

    @property
    def global_freeze_scope(self) -> tuple[str, ...]:
        """The set that becomes the new contract.

        Without a declaration the existing contract is unioned in, so a repository whose
        `Cargo.toml` went away cannot lose clippy from its contract by running `--force`.
        Narrowing the contract stays possible, but only by narrowing the declaration.
        """
        if self.declared is not None:
            return tuple(sorted(self.declared))
        return tuple(sorted(self.detected_analyzers | self.frozen))

    @property
    def scope_mismatches(self) -> frozenset[str]:
        """The analyzers the contract and this run's scope disagree about.

        Empty for a fresh repository: with no contract there is nothing to disagree with, and
        reconciling would make every declared analyzer a mismatch on the very first freeze.
        """
        if not self.frozen:
            return frozenset()
        if self.declared is not None:
            return self.declared ^ self.frozen
        return (self.frozen & self.registered_analyzers) - self.detected_analyzers

    def mismatch(self) -> str | None:
        """Explain a disagreement between the contract and this run's scope, or None if they agree."""
        mismatches = self.scope_mismatches
        if not mismatches:
            return None
        if self.declared is not None:
            unfrozen = sorted(self.declared - self.frozen)
            undeclared = sorted(self.frozen - self.declared)
            lines = [".ebpy/config.json and the frozen contract disagree on the analyzer set:"]
            if unfrozen:
                lines.append(
                    f"  declared but not frozen: {', '.join(unfrozen)} — run `ebpy freeze --analyzer <name>`."
                )
            if undeclared:
                lines.append(
                    f"  frozen but not declared: {', '.join(undeclared)}"
                    " — re-declare it, or `ebpy freeze --force` to drop it."
                )
            return "\n".join(lines)
        return "\n".join(
            [
                "The frozen contract names analyzers this repository no longer evidences:",
                f"  {', '.join(sorted(mismatches))}",
                "Restore what they measure, declare the narrower set in .ebpy/config.json,",
                "or run `ebpy freeze --force` to accept the narrower contract deliberately.",
            ]
        )


def scope_decision(config: EbpyConfig | None, languages: RepoLanguages, state: State) -> ScopeDecision:
    """Assemble the three authorities into one value, projecting languages onto analyzer names.

    The projection lives here and nowhere else, so adding an analyzer keeps exactly one place
    to update — and so `frozen ⊆ detected_analyzers` cannot be misread as a set of languages.
    """
    detected = frozenset(a.name for a in ANALYZERS if a.language in languages.languages)
    return ScopeDecision(
        declared=frozenset(config.analyzers) if config is not None else None,
        detected_analyzers=detected,
        frozen=frozenset(state.frozen_analyzers),
        registered_analyzers=frozenset(a.name for a in ANALYZERS),
    )


def empty_scope_message(decision: ScopeDecision) -> str:
    """Explain a run with nothing to measure. Measuring nothing is not measuring zero."""
    source = "declares no analyzers" if decision.declared is not None else "evidences no supported language"
    return "\n".join(
        [
            f"No analyzer applies here: this repository {source}.",
            "Measuring nothing is not the same as measuring zero, so nothing was written.",
            "Declare the analyzers to ratchet in .ebpy/config.json, or run from the repository root.",
        ]
    )
