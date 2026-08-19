---
name: ebpy-drain
description: Work a frozen Python backlog down one rule at a time — fix the violations, extract the pure function that makes a fix testable, write the test, prune the ceiling, commit. Automates everything it can and opens an issue only for a refactor that genuinely needs the owner's judgment. Use after `ebpy freeze`, or when the user says "backlog を潰して", "リファクタリングして", "drain the baseline", "テストを増やして", "warning を減らして".
---

# ebpy drain

P3. The phase where the value is. Everything before this installs tooling and records a number; this
is where the number comes down and the bugs come out.

**Automate by default.** The only things that stop and ask are the ones where a wrong guess costs
the owner real work — see "What becomes an issue". Everything else you fix, test and commit.

Before the first command, follow the shared
[ebpy command step](../_shared/ebpy-command.md). Every `ebpy` below means the invocation selected
there.

## The loop

One rule per pull request. Not one violation, not the whole backlog.

Work the steps in order and say which one you are on. They are numbered because each depends on the
one before: pruning before the fix reclaims nothing, and a test written after the refactor asserts
the code you just wrote.

### 1. Pick the rule

```bash
ebpy next
```

It ranks the backlog by what the work costs rather than by how big the number is: the files one or
two edits from clean, the rules whose violations sit in the fewest files, the directories where a
rule survives in one last file, and the files heavy enough to leave alone for now. Take the top of
the first list, unless the user named a rule.

**The ranking is per file because the ratchet is per file.** A file with no cell left for a rule
fails on the next violation of it, whatever that rule's total is elsewhere — so two violations in
one file buy more enforcement than twenty spread across twenty files, and the rule with 40
violations in three files is less work than the one with 38 across thirty-one.

### 2. See the actual violations

The baseline hides them from a normal run, so read `.ebpy/baseline.json` for which files carry the
rule, then look at those files directly.

Rule IDs in the baseline are namespaced: `ruff:C901`, `mypy:arg-type`. Strip the prefix to get the
tool's local code:

- **`ruff:*`** — strip the `ruff:` prefix and run `ruff check --select <local-code> <file>`:

  ```bash
  uv run ruff check --select C901 path/to/file.py
  ```

- **`mypy:*`** — run `mypy <file>` and look for findings tagged `[<local-code>]` in the output:

  ```bash
  uv run mypy path/to/file.py
  # look for lines ending in [arg-type], [assignment], etc.
  ```

### 3. Pin what the code does now — before you touch it

A refactor is a change that must **not** alter behaviour, and a test written afterwards cannot say
whether it did: it asserts the code you have just written. So the test goes first, against today's
code, at whatever seam already exists — the public function, the CLI, the route. Run it and watch it
pass. That green is the baseline; when it is still green after the extraction, the extraction is
proven rather than assumed.

If nothing is callable without a filesystem or a network, do not skip the step — take the smallest
seam you can reach and cover that.

For a change that is *supposed* to alter behaviour — a bug the rule uncovered — the same test runs
the other way: write it, watch it fail, then fix.

**When the function is too big to characterise with a handful of tests, keep the old one and diff
against it.** A few hand-written cases cover the branches you thought of, which on a 300-line
function is not the set that matters. The old implementation already knows every answer, so make it
the oracle:

```python
# temporary, deleted in the same PR as the extraction
@pytest.mark.parametrize("payload", REALISTIC_INPUTS)
def test_extraction_matches_the_old_implementation(payload: dict[str, object]) -> None:
    assert new_handler(payload) == _old_handler(payload)
```

### 4. Fix, and extract what makes the fix testable

Most of these rules point at the same thing from different angles: a function doing too much.
`C901` and `PLR0912` say it has too many branches, `PLR0915` too many statements, `ARG001` that an
argument nobody reads is an API lying about what it needs.

The fix is usually to lift the decision out as a pure function — data in, verdict out, no I/O — and
leave the original as the shell that reads the world and calls it. That is what makes the test in
step 3 possible at all, and it is why this phase produces tests rather than just smaller diffs.

Do not add `# noqa`. A suppression comment is a ceiling that never drains and that nothing reports.
If a rule is genuinely wrong for this repository, that is a config decision — see below.

### 5. Prune, and commit the reclaimed ceiling with the fix

```bash
ebpy prune
```

This is the only way the ceiling comes down. Commit `.ebpy/baseline.json` in the same commit as the
fix, so a reviewer sees the violation removed and the ceiling lowered as one change.

### 6. Log what happened

```bash
ebpy log --kind drained --rule ruff:C901 "6 violations; 1 was a real bug — unreachable branch in retry()"
```

The counts are recorded by `prune`; the *reason* exists only if you write it. One entry per commit
as you make it — a batch at the end stamps them all with the wrong commit.

### 7. Verify before opening the PR

```bash
uv run ruff check . && uv run mypy . && uv run pytest && ebpy check
```

All four. `ebpy check` is the one that proves nothing rose.

## What becomes an issue rather than a fix

Open a GitHub issue, name the options, say which one you would pick, and move on:

- **Behaviour that is ambiguous.** Should this throw, retry, or log? The rule found the missing
  case; only the owner knows which answer is right.
- **A public API change.** Narrowing a published signature breaks callers you cannot see.
- **A refactor big enough to be its own project.** A 1,400-line module is not a backlog item.
  Record it with `ebpy log --kind deferred --rule ruff:PLR0915` (or the appropriate namespaced rule)
  too, so it lands in **Carried over** with the commit it was seen at.
- **A rule that may simply be wrong for this repo.** Say which rule, which pattern it fires on, and
  why the pattern is legitimate here. Config changes are the owner's call — and a rule removed
  after a freeze leaves cells nothing will prune, so it needs a `--force` re-freeze afterwards.

Everything else: fix it.

## When a violation turns out to be a real bug

That is the point of this phase, and it changes the shape of the commit: the test comes first and
must **fail**, the fix makes it pass, and the commit message says what was broken rather than which
rule was silenced. Log it as `drained` with the bug named — that entry is the argument for doing
this at all.
