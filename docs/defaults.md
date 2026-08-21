# Default configuration

Everything [`ebpy bootstrap`](cli/bootstrap.md) puts into a repository, and why each value is what
it is. Nothing here is written over a file that already exists — see
[what bootstrap will not do](cli/bootstrap.md#it-never-overwrites-a-config-that-already-exists).

The source of truth is `src/ebpy/generate/configs.py` and `src/ebpy/generate/workflows.py`; this page
is the reading of it.

## At a glance

| Written | Where it lands | Skipped when |
| --- | --- | --- |
| Ruff config | `[tool.ruff]` appended to `pyproject.toml`, or a new `ruff.toml` | any Ruff config is already detected |
| mypy config | `[tool.mypy]` appended to `pyproject.toml`, or a new `mypy.ini` | any mypy config is already detected |
| `.github/workflows/quality.yml` | new file | the path exists |
| `.github/workflows/secret-scan.yml` | new file | the path exists |
| `.github/dependabot.yml` | new file | the path exists |
| `.gitattributes` | new file | the path exists |

Dev dependencies installed, if the diagnosis did not find them: **ruff, mypy, pytest, vulture** —
with the repository's own package manager.

## Ruff

```toml
[tool.ruff]
line-length = 100
target-version = "py311"     # derived; see below

[tool.ruff.lint]
select = [ ... ]

[tool.ruff.lint.mccabe]
max-complexity = 10
```

`target-version` is read from `project.requires-python` — `">=3.12"` becomes `py312` — so the
generated config allows exactly the syntax the package already promises. With no
`requires-python` to read, it falls back to `py311`, the oldest version ebpy itself supports.

### The selected tiers

Each group covers what the others cannot see. That is the whole argument for the list being this
long on day one: with a ceiling recorded, breadth costs nothing.

| Code | Tier | What it catches |
| --- | --- | --- |
| `E`, `W` | pycodestyle | errors and warnings |
| `F` | pyflakes | undefined names, unused imports — real bugs |
| `B` | bugbear | mutable defaults, loop variables captured late |
| `C90` | mccabe | complexity, at `max-complexity = 10` |
| `I` | isort | import order, so diffs stop fighting over it |
| `N` | pep8-naming | naming |
| `UP` | pyupgrade | syntax the `requires-python` already allows |
| `SIM` | simplify | collapsible ifs, needless bool gymnastics |
| `C4` | comprehensions | |
| `ARG` | unused arguments | an argument nobody reads is an API lying about what it needs |
| `PL` | pylint | too many branches, returns, statements |
| `RUF` | ruff-specific | |

No `ignore` list is generated. A rule that is wrong for a repository is a decision for its owner,
and a blanket ignore written by a tool is one nobody can date or justify later.

`ruff format` needs no config of its own — style is settled by the formatter's defaults, once, so no
diff ever argues about it.

## mypy

```toml
[tool.mypy]
strict = true
```

Strict from the start, because plain mypy on untyped code reports almost nothing and looks green.
Type errors are ratcheted **per file per rule** — the same cell model as Ruff — so moving a type
error from one file to another fails `check` even when the total is unchanged.

ebpy supports mypy 1.10 and newer, the floor set by its own dev dependency; the output format is
fixed by the parser's tests. CI runs the full suite against the version the lockfile resolves, and a
separate `mypy-floor` job runs the parser and lifecycle tests against 1.10 so the floor stays real.

ebpy invokes mypy as:

```
mypy . --no-error-summary --show-error-codes --no-pretty --no-color-output
```

`--show-error-codes` ensures rule codes appear regardless of the target repository's mypy config.
`--no-pretty` keeps each finding on one line. `--no-color-output` prevents ANSI escapes from
appearing in rule codes or messages.

This is only ever written into a repository that had **no** mypy config. Turning `strict` on over an
existing loose config is a *tighten* step, done deliberately with the count measured first — so
`diagnose` reports it as a gap and bootstrap leaves it alone.

## `.github/workflows/quality.yml`

```yaml
name: quality
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
```

Least privilege by default: a lint job needs to read the repository and nothing else.

Jobs run on a **three-platform matrix** — `ubuntu-latest`, `macos-latest`, `windows-latest`, with
`fail-fast: false` — because path handling and file watching break per platform, and only per
platform. `fail-fast: false` so one platform's failure does not hide the other two's results.

Steps, in order:

| Step | Command |
| --- | --- |
| Install | the detected manager's own sync |
| Format check | `ruff format --check .` |
| Lint | `ruff check .` |
| Typecheck | `mypy .` |
| Test | `pytest` |
| Ratchet gate | `ebpy check` |
| Lint report | `ebpy report`, with `if: always()` |

The report runs even when the gate has just failed, because that is the run where the backlog is
worth most. It cannot change the exit code — see [report](cli/report.md#it-is-never-a-gate).

### Per package manager

| Manager | Setup | Install | Prefix |
| --- | --- | --- | --- |
| uv | `astral-sh/setup-uv` | `uv sync --all-groups` | `uv run ` |
| poetry | `actions/setup-python` | `pipx install poetry && poetry install` | `poetry run ` |
| pdm | `actions/setup-python` | `pipx install pdm && pdm install -d` | `pdm run ` |
| pipenv | `actions/setup-python` | `pip install pipenv && pipenv install --dev` | `pipenv run ` |
| pip | `actions/setup-python` | `pip install ruff mypy pytest ebpy && pip install -e . \|\| true` | none |

Python **3.12** unless `--python` says otherwise.

## `.github/workflows/secret-scan.yml`

```yaml
      - uses: actions/checkout@<sha>
        with:
          fetch-depth: 0
```

`fetch-depth: 0` because a shallow clone misses the commit that leaked.

It installs the **gitleaks CLI** (MIT) rather than `gitleaks-action`, which needs a licence key
under a GitHub Organization. The download is verified against a **SHA-256 digest** before it runs,
because a release asset can be replaced in place under the same tag — and this binary is what
decides whether a leaked credential gets reported. The install script runs under
`set -euo pipefail` rather than trusting the runner's default flags, so the digest check cannot be
lost inside a pipeline.

Then both scans, each `--redact --exit-code 2`:

```yaml
      - name: Scan history
        run: gitleaks git . --redact --exit-code 2
      - name: Scan working tree
        run: gitleaks dir . --redact --exit-code 2
```

Both, because either alone passes a repository that is holding a secret — see
[secrets](cli/secrets.md#why-both-scans). `--redact` so the finding never lands in a public log.

## Pinned actions

Every `uses:` in the generated workflows is pinned to a **full commit SHA**, with the release as a
trailing comment:

```yaml
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
```

A tag is not a pin: whoever owns the action can move `v4` onto new code, and CI would run it without
a diff, with whatever token the job holds. The version comment is not the pin either — it is what
Dependabot reads to learn which release a SHA stands for, so it rewrites the two together.

| Action | Pinned release |
| --- | --- |
| `actions/checkout` | v4.4.0 |
| `actions/setup-python` | v5.6.0 |
| `astral-sh/setup-uv` | v5.4.2 |
| gitleaks CLI (download + digest) | 8.30.1 |

The SHAs and the digest themselves live in `src/ebpy/generate/workflows.py`, which is where to look
when checking what a generated repository actually received.

## `.github/dependabot.yml`

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      actions:
        patterns: ["*"]
```

Pinning without an updater is how a repository ends up frozen on a version with a known hole, so the
actions ebpy pins get an updater in the same breath. Action bumps are **grouped into one pull
request** rather than one per action, because the point is a diff somebody reads, not a queue
somebody rubber-stamps.

## `.gitattributes`

```
* text=auto eol=lf
```

Line endings settled once, per repository, so the Windows leg of the matrix does not report a
diff nobody wrote.

## Thresholds that are not in a config file

These live in ebpy itself and shape what it reports rather than what it enforces:

| Value | Default | Used by |
| --- | --- | --- |
| file size limit | 600 lines | [`diagnose`](cli/diagnose.md) — the split-and-DRY backlog, reported so the limit becomes a choice rather than a number copied from a blog post |
| "one or two edits from clean" | 2 violations | [`next`](cli/next.md), *take these first* |
| "the last files carrying a rule" | 2 files or fewer | [`next`](cli/next.md), directory tails |
| staleness | 30 days, 50 commits, or a commit no longer in the history | [`status`](cli/status.md) |
| generated workflow Python | 3.12 | [`bootstrap --python`](cli/bootstrap.md) |
