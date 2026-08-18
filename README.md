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

```bash
uv add --dev ebpy      # or pip install ebpy, or pipx install ebpy
```

Python 3.11 or later. Works with uv, poetry, pdm, pipenv and pip — the package manager is detected
from the lockfile, and the generated CI workflow uses whichever one it found.

## Drive it yourself

```bash
ebpy diagnose     # read-only: what is missing, and what each gap costs
ebpy bootstrap    # install it, generate the configs
ebpy freeze       # pin today's violations as the ceiling
ebpy check        # CI gate: fail if anything rose
ebpy next         # what to drain first, and what each fix enforces
ebpy report       # where the findings are, as markdown (for a CI job summary)
ebpy secrets      # scan the whole history for committed credentials
ebpy prune        # after a fix: reclaim the ceiling you earned
ebpy catalog      # list the helpers that already exist, so nobody writes a sixth
ebpy log          # record what happened, stamped with the current commit
```

## Hand a repository to Claude Code

The skills in [`skills/`](skills) are the other half: the CLI does what is deterministic, and the
skills do what needs judgment — is this violation a real bug, what deserves an issue rather than a
fix, when to stop and ask. Copy them into a project's `.claude/skills/`, then say:

```
run ebpy on this repo
```

| What you say | What runs |
| --- | --- |
| "run ebpy on this repo", "clean this repo up" | the whole process, unattended — `ebpy-run` |
| "what would ebpy do here" | diagnose and route one phase at a time — `ebpy-guide` |
| "set up linting here", "lint を入れて" | `ebpy-bootstrap` |
| "freeze the baseline" | `ebpy-freeze` |
| "drain the backlog", "リファクタリングして" | `ebpy-drain` |

## What each command does

### `diagnose`

Read-only survey. Reports the package manager, the declared Python version, the framework, which of
Ruff / a formatter / mypy / pytest / vulture / pre-commit / secret scanning are configured, what CI
runs and on which platforms, whether every workflow `uses:` is pinned to a commit SHA, how many
files exceed the size limit, and a gap list with the phase that closes each one.

Pass `--write` to persist `QUALITY.md` and `.ebpy/state.json`. Pass `--json` for the raw diagnosis.

Detection reads **configs, not installs**: a tool installed but never configured enforces nothing,
and a config with no install behind it fails loudly on the first run.

### `bootstrap`

Installs the missing dev dependencies with the repo's own package manager and generates the layers
the approach depends on, each covering what the others cannot see:

| Layer | Tool | What it sees |
| --- | --- | --- |
| function size and complexity | Ruff `C90`, `PL` | long functions, deep nesting, too many branches |
| bug patterns | Ruff `F`, `B`, `SIM` | mutable defaults, loop variables captured late, undefined names |
| types | mypy `strict` | the errors no lint rule can reach |
| style | `ruff format` | settled once, so no diff ever argues about it |
| dead code | vulture | functions and classes nobody calls |

Plus a three-platform quality workflow, a secret-scan workflow, `dependabot.yml`, and
`.gitattributes`. Every action in those workflows is pinned to a full commit SHA with the release
as a trailing comment, and the gitleaks download is checked against a digest — a tag can be moved
onto new code by whoever owns it, and a release asset can be replaced in place. Dependabot is what
keeps those pins from going stale after ebpy has stopped looking.

It **never overwrites a config that already exists** — the exceptions in it have reasons that are
not in the file. `--dry-run` prints the plan and touches nothing.

### `freeze`

Runs Ruff, writes today's per-file per-rule counts to `.ebpy/baseline.json`, records the mypy error
total as a ratcheted counter, and renders `QUALITY.md`. Commit all three together.

Running it a second time is refused: that would grandfather everything added since. Use `prune` to
lower the ceiling, or `--force` if a rule was genuinely reconfigured.

**Syntax errors are reported, not frozen.** A file that does not parse is invisible to every rule,
so recording a count for it would be a lie — freeze names the files instead and asks you to fix them.

### `check`

The CI gate. Fails when any file holds more violations of a rule than its cell allows, or when the
mypy counter rose. Add it to the workflow after lint.

The ratchet is **per file and per rule**, which is stricter than a repo-wide total: a new file has
no cell of its own, so its first violation fails even when the rule's repo-wide count is unchanged.

### `next`

```bash
ebpy next
ebpy next --json
ebpy next --fan-in
```

The drain order, computed rather than guessed. Since the ratchet works per file per rule, the useful
question is not "which rule is smallest" but "which edit enforces the most", and `next` answers it
in four lists:

| Section | What it is for |
| --- | --- |
| take these first | files one or two violations from clean — one edit each, and that rule is enforced there for good |
| rules by files to touch | 40 violations in 3 files and 38 across 31 are the same size in `status` and ten times apart in work |
| the last files carrying a rule in their directory | the tail of a directory nobody finished |
| leave these until last | files whose count is a redesign rather than a backlog |

It reports the last files still *carrying* a rule, which is not the same claim as "the rest of that
directory is clean": a file Ruff never looks at has no cell either, and no arithmetic over the
baseline can tell the two apart.

`--fan-in` adds one number to those rows — how many files import each one — because the other half
of "how hard is this" is how far the fix reaches. It is a flag rather than the default because it
parses **every source file** in the repository. It deliberately **reorders nothing**: fan-in makes a
*type* fix expensive and says nothing about `C901`, where the fix is local however many files import
the module.

### `report`

Markdown: the backlog as a **rule x area** table, so the shape of the debt is visible rather than
just its size. Written to stdout and **appended to `$GITHUB_STEP_SUMMARY`** when that is set, which
is what makes it a CI report without anyone editing a workflow. The generated workflow runs it after
`check` with `if: always()` — the run where the gate has just failed is the run where the backlog is
worth most.

**It is never a gate.** It cannot change an exit code, and it does not fail when the summary file
cannot be written. If Ruff cannot run at all, it falls back to `.ebpy/baseline.json` and says so —
"no debt" and "nobody looked for debt" must not render the same way.

### `secrets`

Runs `gitleaks` over the **history and the working tree** and fails on any finding.

Both scans, because either alone passes a repository that is holding a secret: the history scan
misses the key you pasted an hour ago and have not committed, and a working-tree scan misses the key
that was committed and then deleted — which is still in every clone.

**This is the one thing here with no baseline, and that is the point.** Every other rule records
what exists and holds the line. A committed key is already public, so there is nothing to
grandfather and the fix is rotation, not a commit.

Three answers, not two, because gitleaks reports a finding and its own failure with the same exit
code unless asked otherwise:

| | |
| --- | --- |
| clean | exit 0 |
| secrets found | exit **2**, and the finding, redacted |
| **the scan could not run** | exit **1**, saying so — not a clean result |

That last row matters more than it looks. Outside a git work tree `gitleaks git` logs an error,
scans **zero commits**, and exits 0 with "no leaks found" — a clean bill of health for a scan that
read nothing. This refuses instead.

### `prune`

After you fix a grandfathered violation, its cell is stale. `prune` lowers every cell to what still
exists, reclaiming exactly what you fixed. It can only ever take away, which makes it safe to run at
any point — and it is the only way the ceiling comes down.

### `log`

```bash
ebpy log --kind drained  --rule C901 "6 violations, 1 real bug"
ebpy log --kind deferred --rule PLR0915 "router.py is 1400 lines; its own project"
ebpy log --kind issue    --rule B008 "opened #42 — product decision"
```

Records what happened against the current commit, and it is the only thing that writes the **Work
log** in `QUALITY.md` — every other command records counts, never why. `deferred` is the one that
earns its keep: it renders into a **Carried over** checklist with the commit it was seen at, because
"router.py needs splitting" is useless four hundred commits later unless a reader can tell when it
was true.

### `catalog`

Writes `docs/shared-helpers.md`: every public function, grouped by directory, with the first
sentence of its docstring. Point your CLAUDE.md at it.

It fills the gap between the two scans. A linter sees inside one file; duplication detection only
notices copies once they are textually similar, and two independent implementations of the same idea
rarely are. Nothing else reports the same function written a sixth time under a sixth name.

### `status`

Prints the current phase, the backlog, and the rules with the smallest remaining counts. It leads
with a `STALE` line when the diagnosis is more than thirty days old, fifty commits behind, or was
taken on a commit no longer in this history (a rebase or force-push). The ratchet itself never goes
stale — Ruff maintains it against the current tree — but the gap list, the file sizes and every
deferred note do.

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

## Design

Anything an agent would do slowly or differently on each run belongs in the CLI; anything a markdown
checklist cannot express belongs in a skill.

Zero runtime dependencies.

## License

MIT. Original work © isamu; this port © its contributors.
