# `ebpy freeze`

P2. One command, run once, and it is the commit the whole approach hangs off.

```bash
ebpy freeze
ebpy freeze --force    # deliberately replace the existing or invalid contract
```

It runs Ruff, writes today's **per-file per-rule** counts to `.ebpy/baseline.json`, records the mypy
error total as a ratcheted counter, sets the phase to `drain`, and renders `QUALITY.md`.

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

## mypy gets a counter, not a baseline

Type errors have no per-file suppression mechanism, so their **total** is ratcheted instead: one
number, recorded at the freeze, which `check` fails on if it rises. If mypy could not run, freeze
says so rather than recording a zero — "no type errors" and "nobody measured type errors" must not
read the same way.

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
invalid shape, lacks the expected freeze state, or records Ruff ceilings that disagree with the
other, normal `freeze` exits 1 before running Ruff or writing anything. It never tries to recover a
partial contract: the ledger-only counters and baseline-only per-file cells cannot reconstruct one
another reliably.

Restore both matching files from version control when the old contract matters. Otherwise,
`freeze --force` discards the old contract and measures a complete new one. When recovering from an
invalid pair it also starts a new ledger, because metadata from an invalid state file is not trusted.

## Next

[`ebpy next`](next.md) ranks what to drain first; the [`ebpy-drain` skill](../skills.md#ebpy-drain)
does the work.
