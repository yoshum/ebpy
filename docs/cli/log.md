# `ebpy log`

Records what happened, stamped with the current commit. The only thing that writes the **Work log**
in `QUALITY.md` — every other command records counts, never why.

```bash
ebpy log --kind drained  --rule ruff:C901    "6 violations, 1 real bug — unreachable retry branch"
ebpy log --kind deferred --rule ruff:PLR0915 "router.py is 1400 lines; splitting is its own project"
ebpy log --kind issue    --rule ruff:B008    "opened #42 — mutable default, product decision"
ebpy log --kind drained  --rule mypy:arg-type "narrowed 3 call sites; 1 was a real type mismatch"
ebpy log --kind note                         "enabled mypy strict before freezing"
```

`--kind` defaults to `note`; `--rule` is optional. Empty text, an unknown kind, and an incomplete,
malformed or inconsistent ceiling artifact pair all exit 1 without changing the ledger.

## The four kinds

| Kind | For | Renders into |
| --- | --- | --- |
| `drained` | a rule worked down, and what it turned up | Work log |
| `deferred` | a refactor consciously **not** made | **Carried over** checklist, plus the Work log |
| `issue` | a decision handed to the owner, with the issue number | Work log |
| `note` | anything else worth a commit stamp | Work log |

`deferred` is the one that earns its keep. "router.py needs splitting" is useless four hundred
commits later unless a reader can tell **when it was true** — so it renders as a checklist item
carrying the commit it was seen at, and the next session can check whether the observation still
describes the code.

## One entry per commit, as you make it

The commit stamp is the whole value. A batch written at the end of a session stamps every entry with
the wrong commit, and a `deferred` note pointing at a commit where the observation was not yet true
is worse than no note.

## What it writes

`.ebpy/state.json` and `QUALITY.md`. It runs no tools and touches no counts — the numbers come from
[`freeze`](freeze.md), [`check`](check.md) and [`prune`](prune.md); the reasons exist only if you
write them.
