# `ebpy report`

The backlog as a **rule × area** table, so the shape of the debt is visible rather than just its
size. Markdown to stdout, and appended to `$GITHUB_STEP_SUMMARY` when that is set — which is what
makes it a CI report without anyone editing a workflow.

```bash
ebpy report
ebpy report --json
```

## What is in it

- violations **new since the baseline**, by rule — the ones that just failed the gate;
- the **backlog the ratchet still holds**, as rules against directories. That is the baseline
  lowered to what still exists, not today's raw counts, which would include the new violations
  above;
- the mypy error total;
- how many files have findings at all.

Ruff and mypy are measured independently. If Ruff cannot run but mypy can, the report still includes
the mypy total alongside the last known Ruff backlog. If mypy cannot run, the report names why rather
than rendering an unmeasured counter as zero.

## It is not a quality gate

Ruff being unavailable and the summary file being unwritable do not fail the report: it renders
the usable half of the answer and says what was not measured. Findings themselves never change the
exit code.

Invalid inputs are different. If the baseline and ledger are incomplete, malformed or inconsistent,
`report` exits 1 before measuring; treating unreadable or disagreeing ceiling data as an empty
backlog would be a false report. Restore both matching files, or replace the contract explicitly
with `freeze --force`.

The generated workflow runs it after `check` with `if: always()`, because the run where the gate has
just failed is the run where the backlog is worth most.

## If Ruff cannot run

It falls back to `.ebpy/baseline.json` and **says so in the output**. "No debt" and "nobody looked
for debt" must not render the same way — a report that quietly degraded to the last known numbers is
worse than no report.

The JSON form carries the same distinction in `lintFailure` and `mypyFailure`. Either is `null` when
that capability was measured successfully, and otherwise holds everything the tool wrote — the same
lines the human report quotes in its banner, which is usually where the fix is named.

## Reading it

A rule spread thinly across every area is a habit; a rule concentrated in one directory is one
module's history. The first is a tightening decision, the second is an afternoon.
