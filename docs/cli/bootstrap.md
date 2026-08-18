# `ebpy bootstrap`

P1. Installs what the diagnosis said was missing and writes the configs. It does not fix a single
violation, and it must not try to — after bootstrap the repository is full of errors, and
[`freeze`](freeze.md) is what makes them survivable.

```bash
ebpy bootstrap --dry-run          # the exact plan, touching nothing
ebpy bootstrap                    # do it
ebpy bootstrap --python 3.11      # python version for the generated workflow (default: 3.12)
```

## What it installs

Whichever of `ruff`, `mypy`, `pytest` and `vulture` the diagnosis did not find, using the
repository's own package manager:

| Manager | Command |
| --- | --- |
| uv | `uv add --dev …` |
| poetry | `poetry add --group dev …` |
| pdm | `pdm add -d …` |
| pipenv | `pipenv install --dev …` |
| pip | `pip install …` |

## What it writes

| File | When | Why |
| --- | --- | --- |
| `pyproject.toml` (appended) | no Ruff / mypy config yet | the rule tiers the ratchet will freeze |
| `ruff.toml`, `mypy.ini` | no `pyproject.toml` to append to | same configs, standalone |
| `.github/workflows/quality.yml` | absent | lint, typecheck, test and `ebpy check` on three platforms |
| `.github/workflows/secret-scan.yml` | absent | gitleaks over history and working tree |
| `.github/dependabot.yml` | absent | keeps the pinned action SHAs current after ebpy stops looking |
| `.gitattributes` | absent | line endings settled once, per repository |

Every value in those files is listed in [Default configuration](../defaults.md).

## It never overwrites a config that already exists

The exceptions in a config that is already there have reasons that are not written in the file. If a
repository's Ruff config is too narrow, widening it is a *tighten* decision to discuss, not a
silent replacement. Existing files are reported as skipped and left alone; `pyproject.toml` is only
ever **appended** to, and only for a table it does not have.

For the same reason bootstrap does not turn on `mypy strict` over an existing loose config. That is
a tighten step, done deliberately, with the count measured first.

## Format first, in its own commit

If the repository has never been formatted, this is the moment:

```bash
uv run ruff format .
git commit -am "style: format with ruff"
```

Alone, before anything else. A formatting commit touching every file is unreviewable but harmless;
mixing it into the tooling commit makes the tooling change unreviewable too. Freezing before
formatting also bakes format-related violations into the ceiling, which then drops for no reason
anybody can reconstruct later.

## After it runs

1. Check the tools actually run: `ruff check .` and `mypy .` must fail with **violations**, not with
   a config error. A config that cannot load produces zero findings and looks like success.
2. Commit the configs and the workflows.
3. Run [`freeze`](freeze.md). The generated workflow calls `ebpy check`, which fails until a
   baseline exists — so the freeze commit is what turns CI green, and leaving it undone leaves the
   repository red.

## If the install fails

The configs are still written, so `--dry-run` output plus a manual install reaches the same place.
The failure is almost always a lockfile out of sync with `pyproject.toml`, no network, or a version
conflict — report it rather than loosening the repository's own pins to get past it.
