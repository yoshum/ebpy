# `ebpy prune`

The only way the ceiling comes down.

```bash
ebpy prune
```

After you fix a grandfathered violation, its cell is stale — it still permits a violation that no
longer exists. `prune` measures every analyzer in the contract and lowers each cell to what still
exists, reclaiming exactly what you fixed.

## It can only ever take away

No cell is ever raised, which makes it safe to rerun after the ceiling has been frozen and impossible
to use as a second freeze. It refuses before the first freeze, or when the ceiling artifacts are
missing, unreadable, malformed or inconsistent: without a valid pair it cannot prove that every
cell only falls. It never reconstructs one artifact from the other. If nothing was
fixed it reports that nothing was reclaimed. A refusal exits 1 without measuring or writing
anything; a valid no-op exits 0.

The reclaimed count is measured against the baseline **file**, not the ledger: a `check` run since
the fix has already lowered the ledger's current numbers, so comparing that would report every prune
as a no-op.

## Commit it with the fix

```bash
ruff check --select C901 src/app/handler.py   # confirm ruff:C901 is gone
ebpy prune
git add .ebpy/baseline.json src/app/handler.py
```

In the same commit, so a reviewer sees the violation removed and the ceiling lowered as one change.
A fix committed without the prune leaves room for the violation to come back silently.

## What it writes

`.ebpy/baseline.json`, `.ebpy/state.json` and `QUALITY.md`. Each complete analyzer's cells are
lowered independently — Ruff and mypy improvements are each reclaimed in the same run.

## Not a substitute for `freeze --force`

Prune lowers cells to today's reality. If a *rule* was reconfigured — a tier added, a setting
changed — its old ceiling no longer describes the same measurement, and that is the one case for
[`freeze --force`](freeze.md#freezing-twice-is-refused). The same command is the explicit recovery
when an invalid artifact pair should be discarded rather than restored.
