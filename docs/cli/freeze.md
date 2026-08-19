# `ebpy freeze`

P2. One command, run once, and it is the commit the whole approach hangs off.

```bash
ebpy freeze
ebpy freeze --force                 # deliberately replace the existing or invalid contract
ebpy freeze --analyzer NAME         # add one analyzer to an existing contract
ebpy freeze --force --analyzer NAME # replace one analyzer in an existing contract
```

It runs Ruff and mypy, writes today's **per-file per-rule** counts to `.ebpy/baseline.json` with
rule IDs namespaced as `ruff:F401`, `mypy:arg-type` and so on, records the contract in
`.ebpy/state.json`, and renders `QUALITY.md`.

From that commit on, every rule is an error for new code and no existing line had to change.

## Check three things first

1. **Is the formatting commit in?** Freezing before formatting bakes format-related violations into
   the ceiling, and the formatting commit then drops them all at once.
2. **Does the rule set look right?** The ceiling is taken against whatever `select` currently says.
   Adding a tier afterwards is fine — it drains like anything else. *Removing* one afterwards leaves
   cells nothing will ever prune.
3. **Does Ruff parse every file?** See below.

## Syntax errors are reported, not frozen

A file that does not parse is invisible to every rule, so recording a count for it would be a lie —
and it would enter the baseline as "clean" and quietly stay unlinted forever. Freeze names the files
and asks you to fix them, then re-run so they enter the baseline properly. [`check`](check.md)
refuses them for the same reason.

## Every in-scope analyzer must be complete

`freeze` and `freeze --force` both refuse when any in-scope analyzer is unavailable, failed, or
reported findings it could not attribute to a rule. There is no invocation that silently skips an
incomplete analyzer and proceeds.

If an analyzer cannot run, fix the toolchain first — `ebpy bootstrap` can install it. If a file is
intentionally unparseable (a template, a fixture, a legacy file), add it to `exclude` / 
`extend-exclude` in the Ruff config, then re-run.

## The scope × force contract

| Invocation | Artifact precondition | What changes |
| --- | --- | --- |
| `freeze` | Fresh repository, or a pre-freeze ledger. Refused if already frozen. | All analyzers' complete cells become the initial contract. |
| `freeze --force` | Any — overwrites an existing, invalid, or absent contract. | Discards the old contract entirely; all analyzers' complete cells become a new contract. |
| `freeze --analyzer NAME` | A valid frozen pair is required; NAME must not be in the contract yet. | Adds NAME's cells to the existing contract, leaving every other namespace untouched. |
| `freeze --force --analyzer NAME` | A valid frozen pair is required. | Replaces NAME's cells and rules in the existing contract, leaving every other namespace untouched. |

**No invocation removes an analyzer from a contract.** A repository whose toolchain is incomplete
should run `ebpy bootstrap` first, so the first freeze always covers every analyzer. `--force`
governs only the artifact precondition — whether an existing contract may be overwritten — and does
not change which analyzers are in scope.

Scoped operations (`--analyzer NAME`) require a valid pair because they must read and preserve the
existing contract. Invalid pairs can only be recovered by a global `freeze --force`, which discards
everything and starts fresh.

## Adding an analyzer to an existing contract

`freeze --analyzer NAME` exists for a contract whose roster is narrower than the analyzers ebpy
knows — the case that arises when a v1 artifact pair was frozen while mypy could not be measured.
It adds mypy's cells to the contract without touching the Ruff ceiling.

## Commit all three artifacts together

```
.ebpy/baseline.json   the ceiling itself
.ebpy/state.json      the ledger
QUALITY.md            the human view
```

Separately they contradict each other, and a reviewer reading one without the others cannot tell
what happened.

## Then wire the gate

CI must run `ebpy check` after lint. Without it the baseline is a note, not a ratchet — a repository
with thorough CI that never runs the gate enforces nothing and looks identical from the outside.
`ebpy bootstrap` writes that workflow; confirm the step is actually there.

## Freezing twice is refused

The second freeze grandfathers everything added since, which is the one thing the baseline exists to
prevent. A refusal exits 1 without measuring or writing anything, so automation cannot mistake it
for a completed freeze. Two legitimate ways forward:

| | |
| --- | --- |
| [`ebpy prune`](prune.md) | after fixing violations. Reclaims exactly what was fixed and can only lower while both ceiling artifacts are readable. **The normal path.** |
| `ebpy freeze --force` | deliberately replaces the contract. Use it when a rule was genuinely reconfigured, or when the artifact pair is invalid and restoring both matching files is not appropriate. This is the only operation that can move a ceiling **up**. |

## Invalid artifacts fail closed

The baseline and ledger are valid only as a matching pair. If either is missing, unreadable, has an
invalid shape, lacks the expected freeze state, or records ceilings that disagree with the other,
normal `freeze` exits 1 before running any analyzer or writing anything. It never tries to recover a
partial contract: the cell-level data in the two files cannot reconstruct one another reliably.

Restore both matching files from version control when the old contract matters. Otherwise,
`freeze --force` discards the old contract and measures a complete new one. When recovering from an
invalid pair it also starts a new ledger, because metadata from an invalid state file is not trusted.

## Next

[`ebpy next`](next.md) ranks what to drain first; the [`ebpy-drain` skill](../skills.md#ebpy-drain)
does the work.
