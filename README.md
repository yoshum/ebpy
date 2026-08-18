# ebpy

English | [日本語](README.ja.md)

Make an existing Python codebase one that can **only get better**.

A Python port of [ever-better](https://github.com/isamu/ever-better) — same idea, same phases, but
built around Ruff, mypy and pytest instead of ESLint and TypeScript.

It reports what quality tooling a repository is missing, installs it, and records every violation
that exists today as a ceiling. From that commit on, old code is grandfathered and new code is held
to the whole rule set — and the ceiling can fall but never rise.

## Why this exists

Adding a strict linter to an old repository produces four thousand errors and gets reverted. The
usual workaround — set everything to a warning — means nothing is enforced and the count quietly
grows.

ESLint solved this in core with **bulk suppressions**. Ruff has no equivalent, so ebpy carries the
ratchet itself: `freeze` records how many violations each rule has **in each file**, `check` fails
on anything beyond those numbers, and `prune` is the only thing that can lower them. Every rule can
be an error from day one without a single existing line changing.

It is not a linter. It runs *your* Ruff, with *your* config, from *your* virtualenv.

## Install

Not published to a package index. One command bootstraps from Git, installs the bootstrap command's
release version as a development dependency, and puts that version's Claude Code skills in
`.claude/skills`:

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install
```

To require a particular release, pass its exact version to `install`. To use a commit or branch,
pass it with `--ref`:

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install <version>
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install --ref <commit-or-branch>
```

Only exact release versions are accepted; version ranges are not yet supported.

Python 3.11 or later; the one-line installer requires uv. ebpy itself supports uv, poetry, pdm,
pipenv and pip — the package manager is detected from the lockfile, and the generated CI workflow
uses whichever one it found.

## Usage

The skills in [`skills/`](skills) are the other half of this tool. The CLI does what is deterministic
— detect, install, count, render, gate — and the skills do what needs judgment: is this violation a
real bug, what deserves an issue rather than a fix, when to stop and ask. The normal way to use ebpy
is to let a skill drive it, and to reach for the CLI yourself when you want one number.

### Give the skills to Claude Code

`ebpy install` delegates to the newly added dependency's `ebpy skills install` command. It has
therefore already put the five skills and their shared instructions in `.claude/skills`, from the
exact same release or Git ref as the development dependency.

Then say what you want, in plain words. Skills are selected from what you say rather than from a
command you type, so there is no name to remember:

| What you say | What runs | What you get |
| --- | --- | --- |
| "run ebpy on this repo", "clean this repo up" | [`ebpy-run`](docs/skills.md#ebpy-run) | the whole process, unattended — a stack of pull requests |
| "what would ebpy do here" | [`ebpy-guide`](docs/skills.md#ebpy-guide) | a diagnosis, and one phase at a time |
| "set up linting here", "lint を入れて" | [`ebpy-bootstrap`](docs/skills.md#ebpy-bootstrap) | tooling installed, configs and CI written |
| "freeze the baseline" | [`ebpy-freeze`](docs/skills.md#ebpy-freeze) | the ceiling pinned, CI gating on it |
| "drain the backlog", "リファクタリングして" | [`ebpy-drain`](docs/skills.md#ebpy-drain) | one pull request per rule, with tests |

What each one does, insists on, and refuses to do: **[Skill reference](docs/skills.md)**.

### Day one: an untouched repository

```
run ebpy on this repo
```

That hands the whole sequence over. If you would rather see it before it happens, ask *"what would
ebpy do here"* — same phases, one at a time, nothing written until you say so.

Either way the first day produces four commits, in this order, and the order is not negotiable:

| | What happens | Command behind it | What to look at |
| --- | --- | --- | --- |
| 1 | survey — every gap named, with the phase that closes it | [`diagnose`](docs/cli/diagnose.md) | what `select` actually contains, before believing a clean bill of health |
| 2 | formatting, alone, in its own commit | `ruff format .` | nothing — it is unreviewable and harmless, which is exactly why it is separate |
| 3 | install the tooling, write the configs and CI | [`bootstrap`](docs/cli/bootstrap.md) | the `--dry-run` output, then that `ruff check .` fails with *violations* rather than a config error |
| 4 | pin today's violations as the ceiling | [`freeze`](docs/cli/freeze.md) | the number it prints, and that all three artifacts are in one commit |

Formatting lands before linting because otherwise the first drain pull request is a whitespace diff
nobody can review. Freezing lands last because a ceiling taken before formatting drops for no reason
anybody can reconstruct later.

**The freeze is where stopping is free.** From that commit CI rejects any new violation, so the run
reports there — the number, and that draining from here is optional — before it opens the first
drain pull request. Everything after step 4 can stop at any pull request without leaving the
repository worse than it was.

Everything bootstrap writes — every selected rule tier, every pinned action, every threshold — is
listed in **[Default configuration](docs/defaults.md)**. It never overwrites a config that already
exists.

After the freeze, the repository is one that can only get better: old code is grandfathered, new
code is held to the whole rule set, and CI rejects anything that rises.

### Every day after: draining

```
drain the backlog
```

One rule per pull request — not one violation, not all of them. The skill picks the rule with
[`next`](docs/cli/next.md), which ranks by what the work costs rather than by how big the number is,
writes a test that pins today's behaviour *before* touching the code, fixes, then lowers the ceiling
by exactly what it earned:

```bash
ebpy next                                   # which edit enforces the most
ebpy prune                                  # commit this with the fix
ebpy log --kind drained --rule C901 "..."   # the reason; nothing else records it
ebpy check                                  # nothing rose
```

It automates by default and opens an issue only for the four decisions that are genuinely the
owner's — ambiguous behaviour, a public API change, a refactor big enough to be its own project, a
rule that may be wrong for this repository. The full loop is in
[`ebpy-drain`](docs/skills.md#ebpy-drain).

### In CI

The generated workflow already carries the gate; if you wire it yourself, two lines matter:

```yaml
      - run: ebpy check              # fails when a count rose above its ceiling
      - run: ebpy report             # the backlog as a rule × area table
        if: always()
```

[`check`](docs/cli/check.md) is what makes the baseline a ratchet rather than a note.
[`report`](docs/cli/report.md) is never a gate — it appends to the job summary and cannot change an
exit code. [`secrets`](docs/cli/secrets.md) is the one check with no baseline: a committed key is
already public, so it gates from the first run.

### Coming back after a while

```bash
ebpy status                # leads with STALE when the diagnosis describes code that has moved
ebpy diagnose --write      # re-survey, stamped with the current commit
```

The ratchet itself never goes stale — Ruff maintains it against the current tree. It is the
*diagnosis* that ages: the gap list, the file sizes, and every deferred note in **Carried over**.
Re-read that checklist after re-diagnosing and drop what no longer describes anything.

### Driving it yourself

Every command works standalone, in any repository, with or without the skills:

| Command | What it is for |
| --- | --- |
| [`install`](docs/cli/install.md) | add ebpy and its matching Claude Code skills to a uv project |
| [`skills install`](docs/cli/skills-install.md) | copy the installed ebpy package's skills into `.claude/skills` |
| [`diagnose`](docs/cli/diagnose.md) | read-only: what is missing, and what each gap costs |
| [`bootstrap`](docs/cli/bootstrap.md) | install it, generate the configs |
| [`freeze`](docs/cli/freeze.md) | pin today's violations as the ceiling |
| [`check`](docs/cli/check.md) | CI gate: fail if anything rose |
| [`next`](docs/cli/next.md) | what to drain first, and what each fix enforces |
| [`prune`](docs/cli/prune.md) | after a fix: reclaim the ceiling you earned |
| [`status`](docs/cli/status.md) | the current phase, the backlog, and whether it is stale |
| [`report`](docs/cli/report.md) | where the findings are, as markdown (for a CI job summary) |
| [`secrets`](docs/cli/secrets.md) | scan the whole history for committed credentials |
| [`catalog`](docs/cli/catalog.md) | list the helpers that already exist, so nobody writes a sixth |
| [`log`](docs/cli/log.md) | record what happened, stamped with the current commit |

Flags, exit codes and the shared options: **[CLI reference](docs/cli/README.md)**.

## Artifacts

| File | Owner | Commit it |
| --- | --- | --- |
| `.ebpy/baseline.json` | ebpy | yes — it *is* the ceiling |
| `.ebpy/state.json` | ebpy | yes — the ledger |
| `QUALITY.md` | rendered from the ledger | yes — the human view |

`QUALITY.md` is regenerated on every run and carries four sections rendered from the ledger: a
**Worklist** of phases as checkboxes with the smallest remaining rules as sub-items, **Carried over**
for refactors deliberately not made, the **Ratchet** table, and a **Work log**. Anything you write
between the `<!-- ebpy:notes:start -->` markers survives.

## The phases

| Phase | What happens |
| --- | --- |
| P0 diagnose | survey, name every gap |
| P1 bootstrap | install, generate configs |
| P2 freeze | pin the ceiling, gate CI |
| P3 drain | fix one rule at a time; bugs found get tests |
| P4 tighten | add the next rule tier, repeat |
| P5 split & DRY | remove duplication and dead code |

P3 and P5 are where the value is, and they **automate by default**: a fix, an extracted function, a
new test, a deleted orphan — done, not asked about. Only a refactor needing the owner's judgment
becomes a GitHub issue, and that issue says what the options are and which one the agent would pick.

## Documentation

| | |
| --- | --- |
| [Skill reference](docs/skills.md) | what each skill does, what it insists on, and what it refuses to do |
| [CLI reference](docs/cli/README.md) | one page per command, plus flags and exit codes |
| [Default configuration](docs/defaults.md) | every value `bootstrap` writes, and why it is that value |
| [Releasing](docs/release.md) | what a merge into `main` ships, and what decides the version |
| [Shared helpers](docs/shared-helpers.md) | generated by `ebpy catalog` from this repository's own source |

## Differences from ever-better

Not a transliteration — the ideas are the same, the mechanics follow the Python ecosystem:

- **The ratchet is ebpy's own.** ESLint ships `--suppress-all`; Ruff does not, so `freeze`, `check`
  and `prune` implement the per-file-per-rule ledger directly, in the same file shape ESLint uses.
- **mypy gets a counter, not a baseline.** Type errors have no per-file suppression mechanism, so
  their total is ratcheted the way ever-better ratchets ESLint warnings.
- **Syntax errors are named, never counted.** Ruff reports them as `invalid-syntax` with no rule;
  they cannot be grandfathered, so freeze and check both refuse rather than recording a zero.
- **Fan-in resolves Python imports** — relative, absolute, and `src/` layouts — instead of relative
  specifiers.
- No `migrate` or `emit-diff`: JavaScript-to-TypeScript has no Python analogue, and Python has no
  compile step whose output could prove a type-only refactor changed nothing.

## Releases

`main` ships. A merged pull request that changed `src/ebpy/` or `skills/` moves the version — how far
is decided by the Conventional Commits since the last tag — then writes `CHANGELOG.md`, tags the
commit and cuts a GitHub Release. Merges that touch neither release nothing, and nothing is uploaded
to PyPI. It is [python-semantic-release](https://python-semantic-release.readthedocs.io) doing the
work; the rules, and the case for releasing on every merge, are in [docs/release.md](docs/release.md).

## Design

Anything an agent would do slowly or differently on each run belongs in the CLI; anything a markdown
checklist cannot express belongs in a skill.

Zero runtime dependencies.

## License

MIT. Original work © isamu; this port © its contributors.
