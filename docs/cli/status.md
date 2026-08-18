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
regressed  0 rules

smallest remaining backlogs:
    2  C901
    5  ARG001
```

The smallest remaining counts are a starting point, not the drain order —
[`next`](next.md) ranks by what the work costs and what each edit enforces.

## The `STALE` line

It leads with `STALE` and a reason when the diagnosis is more than thirty days old, more than fifty
commits behind, or was taken on a commit no longer in this history — a rebase or a force-push.

All three mean the same thing: file names and counts in the *ledger* may describe code that has
moved. Re-run [`diagnose --write`](diagnose.md) before quoting any of them.

**The ratchet itself never goes stale.** Ruff maintains it against the current tree on every
`check`. It is the diagnosis that ages: the gap list, the file sizes, and every deferred note.

## When there is no ledger

`No .ebpy/state.json here` — the repository has never been diagnosed. Start with
[`diagnose`](diagnose.md).

If either ceiling artifact exists without a valid matching partner, `status` exits 1 instead of
rendering a ledger whose ceiling cannot be trusted.
