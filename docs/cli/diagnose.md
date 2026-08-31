# `ebpy diagnose`

P0. The read-only survey. Every later phase reads what it produces, and it is the only command that
is safe to run against a repository you have never seen.

```bash
ebpy diagnose            # print the survey, touch nothing
ebpy diagnose --write    # also persist .ebpy/state.json and QUALITY.md
ebpy diagnose --json     # the raw diagnosis
```

## Python-only

`diagnose` reads Python sources and Python-specific configuration — every row in the table below
depends on it. On a repository with no Python it refuses outright rather than printing an empty
survey: an empty result would read as a finding ("no framework", "0 files over 600 lines") when it
is really "nothing to look at". `ebpy freeze`, `check`, `prune`, `report`, `status`, `log`,
`secrets` and `next` all still work on such a repository.

## What it reports

| Section | Read from |
| --- | --- |
| package manager | the lockfile — `uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile.lock` — then `[tool.*]` |
| declared Python version | `project.requires-python` |
| framework | a declared dependency on django, fastapi or flask |
| tooling | Ruff, a formatter, mypy (and whether `strict` is on), pytest, vulture, pre-commit, secret scanning, `CLAUDE.md` / `AGENTS.md` / `.cursorrules` |
| CI | whether workflows exist, which runner families they use, whether they run lint / typecheck / tests / `ebpy check`, and every `uses:` still on a tag instead of a commit SHA |
| file sizes | how many files exceed 600 lines, and the ten largest |
| gaps | one entry per missing thing, each naming the phase that closes it |

## Detection reads configs, not installs

A tool that is installed but never configured enforces nothing; a config with no install behind it
fails loudly on the first run. Configs are the half worth detecting, so `ruff` in a dependency group
does not count as Ruff being set up, and a `[tool.ruff]` table does.

Two consequences worth knowing before you quote a clean diagnosis:

- **No gaps is not the same as healthy.** A `[tool.ruff]` table selecting three rules passes the
  tooling check. Read what `select` actually contains.
- **`mypy strict` off is the common trap.** Plain mypy on untyped code reports almost nothing and
  looks green. The count that matters is the one after `strict = true` — which is why that gap is
  filed under *tighten* rather than *bootstrap*: turning it on can produce hundreds of errors, and
  those cannot be grandfathered per file.

One gap is worth reading twice: **secret scanning cannot see GitHub's own push protection.** That is
a repository setting, invisible from a clone, so ignore that gap if you know it is on.

## `--write`

Persists the diagnosis into `.ebpy/state.json` **stamped with the current commit**, and re-renders
`QUALITY.md`. The stamp is what lets [`status`](status.md) say later that the numbers describe code
that has moved. If the ceiling artifacts are incomplete, malformed or inconsistent, `--write`
exits 1 without replacing either one. It does not guess whether partial data still holds a ceiling;
restore both matching files or deliberately replace the contract with `freeze --force`.

Without `--write` nothing is written at all — no ledger, no `QUALITY.md`, no `.ebpy/` directory.

## When to re-run it

Whenever `status` prints a `STALE` line: the diagnosis is over thirty days old, more than fifty
commits behind, or was taken on a commit no longer in this history. The ratchet itself never goes
stale — Ruff maintains it against the current tree — but the gap list, the file sizes and every
deferred note do.

## Next

`ebpy bootstrap` closes the bootstrap-phase gaps. See [bootstrap](bootstrap.md), or hand the whole
phase to the [`ebpy-bootstrap` skill](../skills.md#ebpy-bootstrap).
