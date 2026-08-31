# `ebpy catalog`

Writes `docs/shared-helpers.md`: every public function in the repository, grouped by directory, with
the first sentence of its docstring.

```bash
ebpy catalog
```

Point your `CLAUDE.md` at the generated file, and regenerate it rather than editing it.

## What it is for

It fills the gap between the two scans a repository already has. A linter sees inside one file;
duplication detection only notices copies once they are textually similar, and two independent
implementations of the same idea rarely are.

Nothing else reports the same function written a sixth time under a sixth name — which is the P5
failure this exists to prevent, and the one an agent starting a fresh session is most likely to
commit.

## Python-only

`catalog` walks `.py` files for public callables; it has nothing to extract from any other
language. On a repository with no Python it refuses rather than writing an empty
`docs/shared-helpers.md` — an empty catalog would read as "this repository has no duplication
risk" when it is really "nothing was looked at". `ebpy freeze`, `check`, `prune`, `report`,
`status`, `log`, `secrets` and `next` all still work there.

## What it lists

Public module-level callables — names not starting with `_` — from the repository's own source
files, in directory order, each with its location and the first sentence of its docstring. A helper
with no docstring still appears; the empty cell is the point, since a name alone is what makes
somebody write the seventh copy.

## When to run it

At P5, and any time the helper surface has moved. It is cheap and deterministic: the same tree
always produces the same file, so a diff on `docs/shared-helpers.md` is a diff of the public API.
