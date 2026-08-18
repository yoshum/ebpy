---
description: Run the whole ebpy process on a Python repository unattended — diagnose, install, freeze, then drain the backlog rule by rule until it is empty. Opens issues for the decisions it must not make alone and keeps going. Use when the user hands over a repo with "きれいにして", "全部やっておいて", "品質上げといて", "clean this repo up", "run ebpy on this", or asks for the process to run without supervision.
---

# ebpy run

The unattended mode. The user has handed you a repository and expects to come back to pull
requests, not questions.

**Default to acting.** Everything in this process that can be decided from the code, you decide. Two
short lists bound that: the decisions that become an issue, written down in `ebpy-drain`, and the
three hard stops at the end of this file. If something is on neither, do it.

## Before anything: the working tree must be clean

```bash
git status --porcelain
```

If that prints anything you did not create, stop and ask. The first thing this run does is reformat
every file in the repository, and a format commit on top of somebody's uncommitted work is not a
merge conflict they can resolve — it is their diff rewritten underneath them.

An untracked file whose purpose you think you can see is not an exception. Ask.

## The checklist and the log are in the repo, not in your head

`QUALITY.md` carries three sections this mode depends on, all rendered from `.ebpy/state.json`:

- **Worklist** — the phases as checkboxes, with the smallest remaining rules as sub-items. Work it
  top to bottom. It is derived from the numbers beside it, so it cannot drift from them.
- **Carried over** — refactors deliberately not made, each stamped with the commit it was seen at.
- **Work log** — what was drained, deferred, or turned into an issue, and when.

Record as you go, not at the end:

```bash
uv run ebpy log --kind drained  --rule C901 "6 violations, 1 real bug (unreachable retry branch)"
uv run ebpy log --kind deferred --rule PLR0915 "api/router.py is 1400 lines; splitting is its own project"
uv run ebpy log --kind issue    --rule B008 "opened #42 — mutable default, product decision"
uv run ebpy log --kind note "enabled mypy strict before freezing; the ceiling is from the strict run"
```

The commit stamp is the point. A note saying "router.py needs splitting" is useless six months and
four hundred commits later unless a reader can see when it was true.

**Nothing writes these for you, and in this mode nobody else can.** The counts are recorded by
`freeze` and `prune`; every reason behind them exists only if you write it. One entry per commit as
you make it, and one for each decision as well as each fix — including the tier you left off and the
duplication you chose not to extract. This table is the first thing the owner reads when they come
back to a stack of pull requests.

## The sequence

```bash
uvx ebpy diagnose --write     # P0: the gap list, stamped with the commit
uv run ruff format .          # formatting, alone, in its own commit
uvx ebpy bootstrap            # P1: install and generate
uv run ebpy freeze            # P2: pin the ceiling
uv run ebpy next              # P3: and then the loop, per `ebpy-drain`
```

Each of these is a pull request of its own, in this order: a formatting PR, a tooling PR, a freeze
PR, then one PR per rule. On an untouched repository that is more than a handful — worth saying to
the user before you start, not after.

### Report at the freeze before you open the first drain PR

Freeze is the point where the value is locked in: from that commit CI rejects any new violation, and
everything after it is optional cleanup that can stop at any pull request without leaving the
repository worse. Say so there, in four lines:

- the number — "4,312 violations across 47 rules are now grandfathered";
- new code is held to every rule from here; old code is not;
- a red `ebpy check` means the diff added something — not that the repository is bad;
- draining from here is optional, and stopping after any pull request leaves the repository better
  than it was.

**This is a checkpoint, not a question.** Do not wait for an answer — keep going into P3. The
owner cannot choose to stop at the one place where stopping is free unless somebody tells them it
is there, and after the tenth drain PR the offer is worth much less than it is here.

## Coming back to a repository you have not touched in a while

**Re-diagnose first.** `ebpy status` prints a `STALE` line, and `QUALITY.md` opens with a warning,
when the diagnosis is more than thirty days old, more than fifty commits behind, or was taken on a
commit no longer in this history (a rebase or force-push). All three mean the same thing: file names
and counts in the ledger may describe code that has moved.

```bash
uv run ebpy diagnose --write
```

The ratchet itself never goes stale — Ruff maintains it against the current tree. It is the
*diagnosis* that ages: gap list, file sizes, and every deferred note.

Re-read **Carried over** after re-diagnosing and drop the entries that no longer describe anything.
A stale checklist that nobody prunes is how the list stops being read at all.

## Commit cadence, in someone else's repository

- One rule per pull request. A branch that drains four rules cannot be reverted per rule, and the
  one contentious fix blocks the three uncontentious ones.
- Never force-push a branch the owner may have read.
- Never commit to the default branch.
- Every PR must leave `uv run ebpy check` passing. A red gate on a PR that was supposed to *lower*
  the ceiling is the one failure mode that discredits the whole exercise.

## When to stop and wait

Three cases stop the whole run, and only three:

1. **The working tree was dirty when you arrived** — see above. Before anything, so nothing has
   been written yet when you ask.
2. **The install cannot run at all** (no network, a broken lockfile). Report it and stop — every
   later phase depends on the tools existing.
3. **Two drain pull requests in a row fail CI for a reason you cannot diagnose.** One is a bad fix,
   and you fix it. Two in a row is a loop, and a loop left running produces a queue of pull requests
   nobody can merge — which costs the owner more than the backlog did. Stop and report both
   failures, with what you tried.

Two things look like stops and are not:

- **Something on the issue list in `ebpy-drain`** — open the issue and continue with the next
  rule. Do not wait.
- **CI is red for reasons that predate you.** Say so once, in one place, and keep draining; do not
  fix somebody else's broken test suite silently under a lint PR. It also does not arm the counter
  above: a failure that was there before you started is not one of your two.

Everything else: keep going.

## Finishing

When the backlog reaches zero, do not declare victory and leave. Say what the run produced in terms
the owner can check:

- how many violations were grandfathered at the freeze, and how many remain;
- how many turned out to be real bugs, each named;
- what is in **Carried over** and why;
- which issues were opened, and what decision each one is waiting on;
- what the next tier would be (P4 tighten) and roughly what it would cost.
