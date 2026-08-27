# `ebpy status`

Where this repository stands, in eight lines. Reads the baseline and ledger to verify they form a
valid pair, then renders the ledger — no tools run, nothing is written.

```bash
ebpy status
ebpy status --json    # the whole ledger
```

```
phase      drain
frozen     2026-08-18T00:07:45Z
backlog    4312
improved   6 rules

smallest remaining backlogs:
    2  ruff:C901
    5  ruff:ARG001
```

The smallest remaining counts are a starting point, not the drain order —
[`next`](next.md) ranks by what the work costs and what each edit enforces.

## The `STALE` line

It leads with `STALE` and a reason when the diagnosis is more than thirty days old, more than fifty
commits behind, or was taken on a commit whose distance from HEAD cannot be established — a rebase,
a force-push, or a shallow clone.

All of them mean the same thing: file names and counts in the *ledger* may describe code that has
moved. Re-run [`diagnose --write`](diagnose.md) before quoting any of them.

## Shallow clones report an unknown distance, not a small one

In a shallow clone ebpy does not count commits at all. `.ebpy` names the commit the diagnosis was
taken at, and `git rev-list --count` will happily measure from it — but the walk stops at every
graft boundary, so the answer is systematically low and arrives with exit 0. A clone truncated to
the last few commits can report a diagnosis five hundred commits behind as forty, which is under
the threshold and therefore prints as current.

The endpoint being present does not make the number safe: a boundary's parent commit can be on
disk and still be unreachable, because shallowness is a declared cut rather than a missing object.
So `status` asks git whether the clone is complete and, when it is not, says
`HEAD moved since the diagnosis and the distance is unknown` instead of a number it cannot stand
behind. A git too old to answer (`--is-shallow-repository` arrived in 2.15) is treated the same way.

Full history — `fetch-depth: 0` on `actions/checkout`, or `git fetch --unshallow` locally — restores
the count.

**The ratchet itself never goes stale.** Ruff maintains it against the current tree on every
`check`. It is the diagnosis that ages: the gap list, the file sizes, and every deferred note.

## `--json`

`--json` returns the ledger as the full state v2 object, including `frozenAnalyzers` — the list of
analyzers whose ceilings are active in the contract. The v1 field `counters` is not present in v2
state.

## When there is no ledger

`No .ebpy/state.json here` — the repository has never been diagnosed. Start with
[`diagnose`](diagnose.md).

If either ceiling artifact exists without a valid matching partner, `status` exits 1 instead of
rendering a ledger whose ceiling cannot be trusted.
