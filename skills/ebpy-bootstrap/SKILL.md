---
name: ebpy-bootstrap
description: Install Ruff, mypy, pytest and the CI gate into a Python repository that has none of them, and generate the configs. Use when the user says "lint を入れて", "set up linting here", "型チェック入れて", "add CI", "この repo に品質ツールを入れて", or when a diagnosis reported bootstrap-phase gaps.
---

# ebpy bootstrap

P1. The repository has no rules, or has some and enforces none. This phase installs the tooling and
generates the configs; it does not fix a single violation, and it must not try to.

## Order

Before the first command, follow the shared
[ebpy command step](../_shared/ebpy-command.md). Every `ebpy` below means the invocation selected
there.

```bash
ebpy diagnose            # read what is missing
ebpy bootstrap --dry-run # what it would do, exactly
ebpy bootstrap           # do it
```

Read the dry run before running it for real, especially in a repository you did not set up. The
plan names every file it will write and every config it will skip.

## Format first, in its own commit

If the repository has never been formatted, this is the moment:

```bash
uv run ruff format .
git commit -am "style: format with ruff"
```

Alone, before anything else. A formatting commit touching every file is unreviewable but harmless,
and mixing it into the tooling commit makes the tooling change unreviewable too.

## What bootstrap will not do, and why

- **It never overwrites an existing config.** The exceptions in a config that is already there have
  reasons that are not written in the file. If a repo's Ruff config is too narrow, widening it is a
  *tighten* decision — discuss it, do not silently replace it. Bootstrap prints the config it held
  back so that difference can be read; pasting that text over the existing file is the silent
  replacement this rule exists to prevent.
- **It does not fix violations.** After bootstrap the repository is full of errors, and that is the
  expected state. `freeze` is what makes them survivable.
- **It does not enable `mypy strict` on an existing loose config.** Turning it on can produce
  hundreds of errors that cannot be grandfathered per file. That is a `tighten` step, done
  deliberately, with the count measured first.

## After it runs

1. Check that the tools actually run: `uv run ruff check .` and `uv run mypy .` must fail with
   *violations*, not with a config error. A config that cannot load produces zero findings and
   looks like success.
2. **If bootstrap printed configs it held back, do not apply them yourself.** Read each one against
   what the repository already has, then state a proposal and get the user's decision before
   touching the file: which rule tiers of ebpy's defaults are missing, which of the repository's own
   exceptions you would keep and why, and what turning each one on is likely to cost. Merging is by
   *key* — a `pyproject.toml` that already has a `[tool.ruff]` table cannot take a second one.
3. Commit the configs and the workflows.
4. Route to `ebpy-freeze`. The gate in the generated workflow calls `ebpy check`, which fails until
   a baseline exists — so the freeze commit is what turns CI green, and leaving it undone leaves the
   repository red.

## If the install step fails

The install uses the repository's own package manager, detected from its lockfile. A failure there
is almost always one of:

- a lockfile out of sync with `pyproject.toml` — the manager refuses to install; run its own sync
  first;
- no network in this environment — say so plainly rather than switching to a different manager;
- a version conflict — report the conflict, do not resolve it by loosening the repo's own pins.

The configs are still written, so `--dry-run` output plus a manual install gets to the same place.
