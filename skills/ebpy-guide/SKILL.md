---
description: Diagnose a Python repository's quality tooling and route to the right phase, one at a time, explaining what each one buys. Use when the user asks "what would ebpy do here", "where do I start with this codebase", "この repo の品質どうなってる", or wants to understand the process before running it rather than handing the whole thing over.
---

# ebpy

The router. The user wants to know where this repository stands before committing to the process,
or wants one phase rather than all of them.

Start by looking, not by installing:

```bash
uvx ebpy diagnose
```

Read the gap list out loud in your answer. Each gap names the phase that closes it, and the phases
run in order because each depends on the one before.

## What each phase buys, and why the order is fixed

| Phase | Buys | Why it cannot come later |
| --- | --- | --- |
| P0 diagnose | the gap list, the ledger, the commit it was taken at | every later phase reads it |
| P1 bootstrap | Ruff, mypy, pytest, CI, the configs | there is nothing to freeze without rules |
| P2 freeze | the ceiling, and CI that rejects a regression | freezing *after* draining grandfathers the work you just did |
| P3 drain | the backlog falling, and the bugs it contains | needs a ceiling to fall from |
| P4 tighten | the next rule tier | needs the current tier at zero, or the counts blur together |
| P5 split & DRY | duplication and dead code gone | needs tests, which drain writes |

**Formatting lands before linting.** If the repository has never been formatted, run
`ruff format` and commit that alone, first. Otherwise the first drain pull request is a
whitespace diff nobody can review, and the real change hides inside it.

## Routing

| What the user wants | Skill |
| --- | --- |
| the whole thing, unattended | `ebpy-run` |
| set up linting, type checking, CI | `ebpy-bootstrap` |
| pin the baseline | `ebpy-freeze` |
| work the backlog down | `ebpy-drain` |

Never name a skill to the user. Route silently and say what you are doing in plain terms.

## Reading a diagnosis honestly

- **A repository with no gaps is not necessarily healthy.** `diagnose` reads configs. A repo with
  Ruff configured to three rules passes the tooling check and enforces nearly nothing. Look at
  what `select` actually contains before saying the tooling is fine.
- **`mypy strict` off is the common trap.** Plain `mypy` on untyped code reports almost nothing
  and looks green. The count that matters is the one after `strict = true`.
- **A `STALE` line means the numbers describe code that has moved.** Re-run
  `ebpy diagnose --write` before quoting any of them.
- **Secret scanning has no baseline.** If that gap is open, it is the one thing worth doing before
  anything else in this list — a committed key is already public.

## What this skill does not do

It does not install. If the user wants the work done rather than described, route to
`ebpy-bootstrap` or `ebpy-run` and say so once.
