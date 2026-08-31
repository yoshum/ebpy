# `ebpy freeze`

P2. One command, run once, and it is the commit the whole approach hangs off.

```bash
ebpy freeze
ebpy freeze --force                 # deliberately replace the existing or invalid contract
ebpy freeze --analyzer NAME         # add one analyzer to an existing contract
ebpy freeze --force --analyzer NAME # replace one analyzer in an existing contract
```

It measures every analyzer in scope for this repository — Ruff and mypy for Python, clippy for
Rust — writes today's **per-file per-rule** counts to `.ebpy/baseline.json` with rule IDs
namespaced as `ruff:F401`, `mypy:arg-type`, `clippy:clippy::needless_return` and so on, records the
contract in `.ebpy/state.json`, and renders `QUALITY.md`.

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

## When nothing applies

A global `freeze` refuses if the contract it would write is empty: `.ebpy/config.json` declares no
analyzers, or (with no declaration) the repository evidences none of Ruff, mypy or clippy's
languages **and** no earlier contract already covered one — an existing frozen roster is carried
through even when its language later disappears, so a `Cargo.toml` removed by mistake cannot
silently drop clippy from the contract. `freeze --analyzer NAME` refuses on a related but distinct
condition: NAME itself not being in this run's detected or declared scope. Declare it in
`.ebpy/config.json`, or check that what it measures is actually present here. Either refusal writes
nothing — measuring nothing is not the same as measuring zero.

## Coverage clippy could not measure

If a Rust workspace clippy measures does not compile in the configuration ebpy uses — typically
because it references items hidden behind a `cfg` — the freeze message names it: "N workspace(s)
not measured in this configuration: ...". That workspace's packages are recorded as outside the
contract's coverage once this freeze completes, and [`check`](check.md), `prune` and `report` all
then say the same thing about it on every later run, until clippy measures it again.

This can only ever *narrow* an existing clippy contract under `--force`. An ordinary freeze cannot
walk into that state on its own: re-freezing an analyzer already in the contract is refused before
measurement even runs, coverage aside — "already frozen" for a global freeze, "already in the
frozen contract" for `freeze --analyzer clippy`. `--force` is what lets you replace an existing
contract, and a coverage drop found while doing so is accepted as part of that deliberate
replacement rather than refused a second time. It is
[`check`](check.md#a-workspace-clippy-can-no-longer-measure) and
[`prune`](prune.md#a-workspace-clippy-can-no-longer-measure) that refuse — they run against an
already-frozen contract on every invocation, so a coverage drop is exactly the kind of surprise
they exist to catch.

## The scope × force contract

| Invocation | Artifact precondition | What changes |
| --- | --- | --- |
| `freeze` | Fresh repository, or a pre-freeze ledger. Refused if already frozen. | The in-scope set's complete cells become the initial contract. |
| `freeze --force` | Any — overwrites an existing, invalid, or absent contract. | Discards the old contract entirely; the in-scope set's complete cells become a new contract. |
| `freeze --analyzer NAME` | A fresh pair, or a valid frozen pair; NAME must not be in the contract yet. | On a fresh pair, builds a narrow contract holding only NAME. On a frozen pair, adds NAME's cells to the existing contract, leaving every other namespace untouched. |
| `freeze --force --analyzer NAME` | A fresh pair, or a valid frozen pair. | Replaces (or on a fresh pair, installs) NAME's cells and rules, leaving every other namespace untouched. |

A global freeze's "in-scope set" is `.ebpy/config.json`'s declared analyzers when there is a
declaration, or detected analyzers unioned with whatever is already frozen when there is not — so
an undeclared repository can never lose an analyzer from its contract just because the language
that justified it (e.g. a `Cargo.toml`) went away. **No invocation narrows a contract implicitly.**
The only way to drop an analyzer is to declare a narrower set in `.ebpy/config.json` and run
`ebpy freeze --force`: `--force` alone only governs the artifact precondition, but combined with a
narrowed declaration it becomes the in-scope set for the new contract, and analyzers that fall out
of it are dropped. This is the recovery path the mismatch message itself names when the frozen
contract and the declaration disagree.

Scoped operations (`--analyzer NAME`) accept a fresh pair or a valid frozen pair. On a fresh pair
they build a narrow contract from the start; on a frozen pair they read and preserve the existing
contract. Only invalid pairs are refused — a partial contract cannot be read and preserved, so
recovering it needs a global `freeze --force`, which discards everything and starts fresh.

## Building a narrow contract, or adding an analyzer later

`freeze --analyzer NAME` covers two cases where the roster is narrower than every analyzer this ebpy
ships:

- **Staged adoption within a version.** A repository whose toolchain is not yet complete — mypy not
  installed, say — can freeze the analyzer it *can* measure today with `freeze --analyzer ruff`,
  building a ruff-only contract from a fresh pair. [`check`](check.md) then gates ruff and names
  mypy as a configured analyzer the contract does not yet hold. Add it with
  `freeze --analyzer mypy` once the toolchain is complete.
- **A new analyzer across versions.** A later ebpy that adds a new analyzer inherits a contract an
  earlier ebpy pinned before that analyzer existed. `freeze --analyzer NAME` brings the new analyzer
  under the ceiling without re-pinning — and so without grandfathering — any of the existing
  namespaces.

There is no migration path from before version 2: a version-1 contract is refused outright, and the
only way past it is a global `freeze --force` that discards the old contract entirely.

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
