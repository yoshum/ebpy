# Skill reference

The CLI does what is deterministic — detect, install, count, render, gate. The skills do what needs
judgment: is this violation a real bug, is this duplication or coincidence, what deserves an issue
rather than a fix, when to stop and ask.

There are five, and they are not five ways of saying the same thing. One routes, one installs, one
pins the ceiling, one drains the backlog, and one does the whole sequence without asking.

## Installing them

```bash
mkdir -p .claude/skills
cp -r path/to/ebpy/skills/* .claude/skills/
```

Then talk to Claude Code normally. Skills are selected from what you say, not from a command you
type, so "lint を入れて" and "set up linting here" reach the same one. **Never ask for a skill by
name** — say what you want done.

All five skills use one shared command-resolution step. It uses the project's own runner when
`ebpy` is already installed there. Otherwise it asks to add `ebpy` to the project's development
dependencies, so the command version is recorded alongside the skills that drive it. If the user
refuses that install, it falls back to
`uvx --from "git+https://github.com/yoshum/ebpy" ebpy`. Individual skill files write only `ebpy`;
the shared step supplies the concrete invocation.

## Which one runs

| What you say | Skill | What you get back |
| --- | --- | --- |
| "run ebpy on this repo", "きれいにして", "全部やっておいて" | [`ebpy-run`](#ebpy-run) | a stack of pull requests, and issues for the decisions it must not make alone |
| "what would ebpy do here", "この repo の品質どうなってる" | [`ebpy-guide`](#ebpy-guide) | a diagnosis read out loud, and one phase at a time |
| "set up linting here", "lint を入れて", "add CI" | [`ebpy-bootstrap`](#ebpy-bootstrap) | tooling installed, configs and workflows written |
| "freeze the baseline", "ベースラインを固定して" | [`ebpy-freeze`](#ebpy-freeze) | the ceiling pinned, CI gating on it |
| "drain the backlog", "リファクタリングして", "warning を減らして" | [`ebpy-drain`](#ebpy-drain) | one pull request per rule, with tests |

`ebpy-guide` and `ebpy-run` are the two entry points, and the difference between them is how much
you want to be asked. The other three are phases: reachable directly, and routed to by the first
two.

---

## `ebpy-guide`

**The router. Use it when you want to understand before you commit.**

It starts by looking rather than installing — `ebpy diagnose`, read out loud, with each gap named
alongside the phase that closes it. Then it routes one phase at a time and explains what that phase
buys.

Reach for it when you have inherited a repository and do not yet know whether it needs everything or
one thing; when you want the gap list without anything being written; or when somebody else's repo
is involved and an unattended run would be presumptuous.

**What it insists on**

- **The phase order is fixed**, and it will say why rather than skipping: there is nothing to freeze
  without rules, and freezing *after* draining grandfathers the work you just did.
- **Formatting lands before linting.** Otherwise the first drain pull request is a whitespace diff
  nobody can review, with the real change hidden inside it.
- **A repository with no gaps is not necessarily healthy.** `diagnose` reads configs, so a Ruff
  config selecting three rules passes the check while enforcing nearly nothing. The skill looks at
  what `select` actually contains before calling the tooling fine.
- **Secret scanning has no baseline.** If that gap is open it is the one thing worth doing before
  anything else on the list — a committed key is already public.

**What it does not do:** install or configure the repository's quality tools. Resolving the `ebpy`
command itself is the shared prerequisite; if you want the quality work done rather than described,
it routes to `ebpy-bootstrap` or `ebpy-run` and says so once.

Drives: [`diagnose`](cli/diagnose.md), [`status`](cli/status.md).

---

## `ebpy-bootstrap`

**P1. Use it when the repository has no rules, or has some and enforces none.**

It installs the tooling and generates the configs — and it fixes **nothing**. After it runs the
repository is full of errors, and that is the expected state; `freeze` is what makes them survivable.
Every default it writes is listed in [Default configuration](defaults.md).

Reach for it when a diagnosis reported bootstrap-phase gaps, or when somebody asks for linting, type
checking or CI in a repository that has none.

**What it insists on**

- **Read the dry run first.** `ebpy bootstrap --dry-run` names every file it will write and every
  config it will skip. In a repository you did not set up, that reading is the whole safety margin.
- **The formatting commit goes first, alone.** Before the tooling commit, so both stay reviewable.
- **It never overwrites an existing config.** The exceptions in a config that is already there have
  reasons that are not in the file. Widening a too-narrow Ruff config is a *tighten* decision to
  discuss, not a silent replacement.
- **It does not turn on `mypy strict` over an existing loose config.** That can produce hundreds of
  errors which cannot be grandfathered per file — a deliberate step, with the count measured first.
- **It verifies the tools actually run afterwards.** `ruff check .` must fail with *violations*, not
  with a config error: a config that cannot load produces zero findings and looks like success.

**Where it hands off:** to `ebpy-freeze`, always. The generated workflow calls `ebpy check`, which
fails until a baseline exists — so bootstrap without freeze leaves CI red.

**When the install fails** it reports the cause — a lockfile out of sync, no network, a version
conflict — rather than switching package managers or loosening the repository's own pins. The
configs are written either way.

Drives: [`diagnose`](cli/diagnose.md), [`bootstrap`](cli/bootstrap.md).

---

## `ebpy-freeze`

**P2. One command, run once, and it is the commit the whole approach hangs off.**

It pins today's per-file per-rule counts as the ceiling, records the mypy total as a ratcheted
counter, renders `QUALITY.md`, and makes sure CI actually gates on the result.

Reach for it straight after bootstrap, or when somebody says "grandfather what is there and stop the
new stuff".

**What it checks before running**

1. **Is the formatting commit in?** Freezing first bakes format violations into the ceiling, which
   then drops all at once for no reason anybody can reconstruct later.
2. **Does the rule set look right?** The ceiling is taken against whatever `select` says now. Adding
   a tier later is fine; *removing* one later leaves cells nothing will ever prune.
3. **Does Ruff parse everything?** A file that does not parse is invisible to every rule, so it
   would enter the baseline as "clean" and stay unlinted. Freeze names those files and refuses to
   count them.

**What it insists on afterwards**

- **All three artifacts in one commit** — `.ebpy/baseline.json`, `.ebpy/state.json`, `QUALITY.md`.
  Separately they contradict each other.
- **The gate is actually wired.** A baseline with nothing running `ebpy check` is a note, not a
  ratchet, and a repository like that looks identical from the outside to one that enforces.
- **Never freeze twice.** The second freeze grandfathers everything added since — `prune` is the
  normal way down. `--force` deliberately replaces the contract, for a genuinely reconfigured rule
  or an invalid artifact pair that should be discarded rather than restored.

**What it tells you at the end:** four lines, because this commit is the one worth stopping on —
the number ("4,312 violations across 47 rules are now grandfathered"), that new code is held to
every rule from here and old code is not, that a red `ebpy check` means the diff added something
rather than that the repository is bad, and that draining from here is optional. CI already rejects
any new violation, so stopping after any pull request leaves the repository better, never worse.

Drives: [`freeze`](cli/freeze.md), [`check`](cli/check.md), [`prune`](cli/prune.md).

---

## `ebpy-drain`

**P3. The phase where the value is — and the one you will run most often.**

Everything before it installs tooling and records a number. This is where the number comes down and
the bugs come out. **One rule per pull request**: not one violation, not the whole backlog.

Reach for it after a freeze, whenever there is a backlog and time to spend on it, or when somebody
asks for refactoring, fewer warnings, or more tests.

**The loop, in order** — the order is the point, since pruning before the fix reclaims nothing and a
test written after the refactor asserts the code that was just written:

1. **Pick the rule** with [`ebpy next`](cli/next.md), which ranks by what the work costs rather than
   by how big the number is.
2. **See the actual violations.** The baseline hides them from a normal run, so it reads the
   baseline file and then `ruff check --select <RULE> <file>`.
3. **Pin what the code does now, before touching it.** A refactor must not change behaviour, and a
   test written afterwards cannot say whether it did. When a function is too big to characterise
   with a handful of cases, it keeps the old implementation as an oracle and diffs against it, then
   deletes it in the same pull request.
4. **Fix, and extract what makes the fix testable** — usually lifting the decision out as a pure
   function and leaving the original as the shell that reads the world. That is why this phase
   produces tests rather than just smaller diffs.
5. **`ebpy prune`**, committed with the fix, so a reviewer sees the violation removed and the
   ceiling lowered as one change.
6. **`ebpy log`** the reason. The counts are recorded for you; the *why* exists only if it is
   written, and one entry per commit as you go — a batch at the end stamps them all with the wrong
   commit.
7. **Verify all four:** `ruff check .`, `mypy .`, `pytest`, `ebpy check`.

**It automates by default.** A fix, an extracted function, a new test, a deleted orphan — done, not
asked about. Four things become a GitHub issue instead, each with the options named and a
recommendation:

- behaviour that is genuinely ambiguous (throw, retry, or log?);
- a public API change, which breaks callers nobody can see;
- a refactor big enough to be its own project — also logged as `deferred`, so it lands in **Carried
  over** with the commit it was seen at;
- a rule that may simply be wrong for this repository, which is a config decision and the owner's
  call.

**It never adds `# noqa`.** A suppression comment is a ceiling that never drains and that nothing
reports.

**When a violation turns out to be a real bug**, the shape of the commit changes: the test comes
first and must fail, the fix makes it pass, and the message says what was broken rather than which
rule was silenced.

Drives: [`next`](cli/next.md), [`prune`](cli/prune.md), [`log`](cli/log.md), [`check`](cli/check.md).

---

## `ebpy-run`

**The unattended mode. You hand over a repository and come back to pull requests, not questions.**

It runs the whole sequence — diagnose, format, bootstrap, freeze, then drain rule by rule until the
backlog is empty — and defaults to acting. The list of things that stop and ask is short, written
down in `ebpy-drain`, and everything not on it gets done.

Reach for it when the repository is yours or you have the mandate, and when a stack of pull requests
is a welcome outcome rather than a surprise. On an untouched repository that stack is more than a
handful, which is worth saying before it starts rather than after.

**The sequence**, one pull request per step, in this order: a formatting PR, a tooling PR, a freeze
PR, then one PR per rule.

**Before it touches anything** it checks that the working tree is clean. The first thing the run
does is reformat every file, and a format commit on top of somebody's uncommitted work is not a
merge conflict they can resolve — it is their diff rewritten underneath them. A dirty tree stops
the run before a single file has been written.

**It reports at the freeze.** That commit is where the value is locked in — CI rejects any new
violation from there, and everything after it is optional cleanup that can stop at any pull request
without leaving the repository worse. So it says so at that point rather than after the tenth drain
PR: the number, that new code is now held to every rule, that a red `check` means the diff added
something, and that stopping here is free. It is a checkpoint, not a question — it does not wait
for an answer.

**What keeps it honest**

- **The checklist and the log are in the repository, not in its head.** `QUALITY.md` carries the
  Worklist (phases as checkboxes, derived from the numbers beside them, so it cannot drift), Carried
  over, and the Work log. It records as it goes, including the tier it left off and the duplication
  it chose not to extract — that table is the first thing an owner reads when they come back.
- **Commit cadence in somebody else's repository:** one rule per pull request, never force-push a
  branch the owner may have read, never commit to the default branch, and every PR leaves
  `ebpy check` passing. A red gate on a PR that was supposed to *lower* the ceiling is the failure
  mode that discredits the whole exercise.
- **Exactly three things stop the whole run:** a dirty working tree at the start, an install that
  cannot run at all (no network, a broken lockfile — every later phase depends on the tools
  existing), and **two drain pull requests in a row failing CI for a reason it cannot diagnose**.
  One failure is a bad fix, which it fixes; two in a row is a loop, and a loop left running produces
  a queue of pull requests nobody can merge — which costs more than the backlog did.
- **Two things look like stops and are not:** an issue-list item (open the issue, continue with the
  next rule, do not wait), and CI that was already red before it arrived (say so once, keep
  draining, never silently fix somebody else's test suite under a lint PR — and it does not count
  toward the two failures above, since it was not caused by a drain PR).
- **Coming back after a while, it re-diagnoses first**, then re-reads Carried over and drops the
  entries that no longer describe anything. A stale checklist nobody prunes is how the list stops
  being read.

**How it finishes:** not with "done", but with what the run produced — how many violations were
grandfathered and how many remain, how many turned out to be real bugs and which, what is in Carried
over and why, which issues are open and what decision each is waiting on, and what the next tier
would cost.

Drives: every command.

---

## Writing your own

The division is the same one the [design](../README.md#design) note states: anything an agent would
do slowly or differently on each run belongs in the CLI; anything a markdown checklist cannot
express belongs in a skill. If you find yourself writing a skill step that is really an algorithm —
counting, ranking, detecting — that is a CLI command waiting to be written, and it will be faster
and identical on every run.
