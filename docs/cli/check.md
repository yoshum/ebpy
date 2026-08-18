# `ebpy check`

The CI gate. It is the only thing that makes the baseline a ratchet rather than a note.

```bash
ebpy check
ebpy check --no-write    # do not update the ledger or QUALITY.md
```

Exit 0 when nothing rose; exit 1 with the reason when something did.

## What fails it

| Failure | Message |
| --- | --- |
| a file holds more violations of a rule than its cell allows | the count beyond the ceiling, plus the five worst rules |
| a ratcheted counter grew (`mypy:errors`) | `name: baseline -> current` |
| Ruff could not parse a file | the syntax errors, named |
| there is no baseline at all | run `ebpy freeze` and commit the result |

## The ratchet is per file and per rule

Stricter than a repo-wide total, deliberately: a new file has **no cell of its own**, so its first
violation fails even when that rule's repo-wide count is unchanged. Moving code into a new file does
not carry its grandfathering with it.

## Syntax errors cannot pass by having no count

A file that does not parse is invisible to every rule, so it has nothing to compare against a
ceiling. Check refuses rather than reading that silence as clean.

## What it writes

By default it records what it observed into `.ebpy/state.json` and re-renders `QUALITY.md`, so the
numbers a human reads are the numbers CI last measured. `--no-write` skips that, for a read-only
environment or a run you do not want to leave a trace.

Observing never raises a ceiling: the recorded baseline is what `freeze` and `prune` set, and a
check run only updates the *current* half of it.

## In CI

The generated workflow runs it after lint, typecheck and tests, then runs
[`report`](report.md) with `if: always()`:

```yaml
      - name: Ratchet gate
        run: uv run ebpy check
      - name: Lint report
        if: always()
        run: uv run ebpy report
```

The run where the gate has just failed is the run where the backlog is worth most.

## When it fails on your pull request

Either the code introduced a violation — fix it — or a rule was genuinely reconfigured, which is the
one case for [`freeze --force`](freeze.md#freezing-twice-is-refused). Do not add `# noqa`: a
suppression comment is a ceiling that never drains and that nothing reports.
