# `ebpy next`

P3. The drain order, computed rather than guessed.

```bash
ebpy next
ebpy next --json
ebpy next --fan-in
```

Since the ratchet works per file per rule, the useful question is not "which rule is smallest" but
**"which edit enforces the most"**. `next` answers it in four lists from the baseline, after
verifying that the baseline and ledger form a valid pair — it runs no tools and writes nothing.

## The four sections

| Section | What it is for |
| --- | --- |
| **take these first** | files within two violations of clean for one rule. One or two edits, and that rule is enforced in that file for good |
| **rules by the files you have to touch** | 40 violations in 3 files and 38 across 31 are the same size in `status` and ten times apart in work |
| **the last files carrying a rule in their directory** | the tail of a directory nobody finished — two files or fewer still holding it |
| **leave these until last** | files whose count is a redesign rather than a backlog |

"Heavy" means **one** rule the file cannot clear in a couple of edits, not a large total: a file
holding two rules at one violation each sums past any cheap threshold while every cell in it is a
quick win.

## What the third section does not claim

It reports the last files still *carrying* a rule, which is not "the rest of that directory is
clean". A file Ruff never looks at has no cell either, and no arithmetic over the baseline can tell
the two apart.

## `--fan-in`

Adds one number to the file rows: how many files import each one — because the other half of "how
hard is this" is how far the fix reaches.

- It is a **flag rather than the default** because it parses every source file in the repository.
- It **reorders nothing.** Fan-in makes a *type* fix expensive and says nothing about `C901`, where
  the fix is local however many modules import it.
- The number is printed only where it is above zero. Printing "imported by 0" on every row of a
  repository that never asked for the graph would read as a measurement rather than an absence.
- **Python-only.** The import graph is built by parsing `.py` files with `ast`; on a repository with
  no Python, `--fan-in` refuses rather than silently printing every row as "imported by 0". Plain
  `ebpy next` (no `--fan-in`) has no such restriction — it ranks whatever the baseline already
  holds, for every analyzer.

## Reading it during a drain

Rule IDs are namespaced in all output — `ruff:C901`, `mypy:arg-type` — so each rank row names both
the analyzer and the local code.

Take the top of the first list unless a rule was named for you. Then read the actual violations —
the baseline hides them from a normal run:

```bash
ruff check --select C901 path/to/file.py   # for a ruff:C901 finding
mypy path/to/file.py                       # for mypy:* findings
```

The whole loop, including what to do with a violation that turns out to be a real bug, is in the
[`ebpy-drain` skill](../skills.md#ebpy-drain).

## When it says nothing is grandfathered

Either the baseline is not frozen yet ([`freeze`](freeze.md)) or the backlog is empty. Those are
different situations and the message says which.

An incomplete, malformed or inconsistent artifact pair is neither case: `next` exits 1 rather than
treating unreadable cells as an empty backlog.
