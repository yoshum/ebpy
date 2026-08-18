# `ebpy prune`

The only way the ceiling comes down.

```bash
ebpy prune
```

After you fix a grandfathered violation, its cell is stale — it still permits a violation that no
longer exists. `prune` runs Ruff and lowers every cell to what still exists, reclaiming exactly what
you fixed.

## It can only ever take away

No cell is ever raised, which makes it safe to run at any point and impossible to use as a second
freeze. If nothing was fixed it reports that nothing was reclaimed.

The reclaimed count is measured against the baseline **file**, not the ledger: a `check` run since
the fix has already lowered the ledger's current numbers, so comparing that would report every prune
as a no-op.

## Commit it with the fix

```bash
ruff check --select C901 src/app/handler.py   # confirm it is gone
ebpy prune
git add .ebpy/baseline.json src/app/handler.py
```

In the same commit, so a reviewer sees the violation removed and the ceiling lowered as one change.
A fix committed without the prune leaves room for the violation to come back silently.

## What it writes

`.ebpy/baseline.json`, `.ebpy/state.json` and `QUALITY.md`. It also refreshes the mypy counter, so
type errors fixed along the way are reclaimed too.

## Not a substitute for `freeze --force`

Prune lowers cells to today's reality. If a *rule* was reconfigured — a tier added, a setting
changed — its old ceiling no longer describes the same measurement, and that is the one case for
[`freeze --force`](freeze.md#freezing-twice-is-refused).
