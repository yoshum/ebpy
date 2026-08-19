---
name: ebpy-freeze
description: Pin a Python repository's current violations as a ceiling so every rule can be an error from today without changing a line, and gate CI on it. Use after bootstrap, or when the user says "ベースラインを固定して", "freeze the baseline", "既存の違反は見逃して新しいのだけ止めて", "grandfather the existing violations".
---

# ebpy freeze

P2. One command, run once, and it is the commit the whole approach hangs off.

Before the first command, follow the shared
[ebpy command step](../_shared/ebpy-command.md). Every `ebpy` below means the invocation selected
there.

```bash
ebpy freeze
```

It runs Ruff and mypy, writes today's per-file per-rule counts to `.ebpy/baseline.json` with rule
IDs namespaced as `ruff:F401`, `mypy:arg-type` and so on, records the contract in `.ebpy/state.json`,
and renders `QUALITY.md`.

## Check three things before you run it

1. **Is the formatting commit in?** Freezing before formatting bakes format-related violations into
   the ceiling, and the formatting commit then drops them all at once — a ceiling that fell for no
   reason anybody can reconstruct later.
2. **Does the rule set look right?** The ceiling is taken against whatever `select` currently says.
   Adding a rule tier afterwards is fine (it drains like any other), but *removing* one afterwards
   leaves cells nothing will ever prune.
3. **Does Ruff run clean of syntax errors?** Freeze reports them and refuses to count them. Fix
   them first — a file that does not parse is invisible to every rule, so it would enter the
   baseline as "clean" and quietly stay unlinted.

## Commit all three artifacts together

```
.ebpy/baseline.json   the ceiling itself
.ebpy/state.json      the ledger
QUALITY.md            the human view
```

Separately they contradict each other, and a reviewer reading one without the others cannot tell
what happened.

## Then wire the gate

CI must run `ebpy check` after lint. Without it the baseline is a note, not a ratchet — a repository
with thorough CI that never runs the gate enforces nothing and looks identical from the outside.
`ebpy bootstrap` writes the workflow; confirm the step is actually there.

## Do not freeze twice

The second freeze grandfathers everything added since, which is the one thing the baseline exists to
prevent — so ebpy refuses it. Two legitimate ways forward:

- **`ebpy prune`** — after fixing violations, reclaims exactly what was fixed and lowers the
  ceiling. This is the normal path and can be run any time.
- **`ebpy freeze --force --analyzer NAME`** — when a rule was genuinely reconfigured (a tier added, a
  rule's settings changed) and its old ceiling no longer describes the same measurement. Re-pins only
  that analyzer's namespace, leaving every other ceiling in place. Prefer this over a global re-pin.
- **`ebpy freeze --force`** — the global re-pin: rebaselines every namespace at once. Use it only when
  recovering from an invalid artifact pair (scoped freeze cannot), since it grandfathers whatever each
  analyzer reports today. This is the only operation that can move a ceiling up. Say in the commit
  message which rule changed and why.

## What to tell the user afterwards

This commit is the one worth stopping on, so report at it rather than rolling straight into the
backlog. Four lines:

- **the number** — "4,312 violations across 47 rules and 2 analyzers are now grandfathered";
- **new code is held to every rule from here; old code is not**;
- **a red `ebpy check` means the diff added something** — not that the repository is bad. That
  sentence prevents the first false conclusion somebody draws from a failing gate;
- **draining is optional from here.** CI already rejects any new violation, so stopping after any
  pull request leaves the repository better than it was, never worse.

Then the next step: `ebpy next` ranks what to drain first, and `ebpy-drain` does the work.
