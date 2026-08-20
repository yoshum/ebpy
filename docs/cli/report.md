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
- per-analyzer status — complete, incomplete, unavailable, or failed — and the details when a
  measurement could not be taken;
- how many files have findings, per analyzer.

Ruff and mypy are measured independently. If Ruff cannot run but mypy can, the report still includes
the mypy backlog alongside the last known Ruff ceiling. If an analyzer cannot run, the report names
why rather than rendering an unmeasured count as zero.

## It is not a quality gate

An analyzer being unavailable and the summary file being unwritable do not fail the report: it
renders the usable half of the answer and says what was not measured. Findings themselves never
change the exit code.

Invalid inputs are different. If the baseline and ledger are incomplete, malformed or inconsistent,
`report` exits 1 before measuring; treating unreadable or disagreeing ceiling data as an empty
backlog would be a false report. Restore both matching files, or replace the contract explicitly
with `freeze --force`.

The generated workflow runs it after `check` with `if: always()`, because the run where the gate has
just failed is the run where the backlog is worth most.

## If an analyzer cannot run

It falls back to `.ebpy/baseline.json` and **says so in the output**. "No debt" and "nobody looked
for debt" must not render the same way — a report that quietly degraded to the last known numbers is
worse than no report.

## JSON schema

> **Breaking change (pre-1.0):** the `--json` schema changed in this release. The previous fields
> `mypyErrors`, the global `filesWithFindings` scalar, `lintFailure`, and `mypyFailure` are
> replaced by the `analyzers` object described below.

The `analyzers` object has one entry per analyzer ebpy attempted to measure:

```json
{
  "newTotal": 1,
  "backlogTotal": 18,
  "newRules": [{"rule": "mypy:arg-type", "count": 1}],
  "sections": [
    {
      "title": "Backlog — grandfathered, drains rule by rule",
      "total": 18,
      "areas": ["src"],
      "rows": [
        {"rule": "ruff:F401", "total": 14, "counts": [14]},
        {"rule": "mypy:arg-type", "total": 4, "counts": [4]}
      ]
    }
  ],
  "analyzers": {
    "mypy": {
      "inContract": true,
      "status": "complete",
      "findings": 5,
      "filesWithFindings": 3,
      "failure": null,
      "unattributedTotal": 0,
      "unattributed": []
    },
    "ruff": {
      "inContract": true,
      "status": "incomplete",
      "findings": 4,
      "filesWithFindings": 2,
      "failure": null,
      "unattributedTotal": 1,
      "unattributed": [
        {"file": "fixtures/broken.py", "line": 7, "message": "Expected an expression"}
      ]
    }
  }
}
```

`analyzers.*.status` is one of `complete`, `incomplete`, `unavailable`, or `failed`.
`findings` is the attributed cell total for a `Measured` analyzer; `null` when unavailable or failed.
`failure` is the bounded multi-line detail when unavailable or failed, otherwise `null`. A detail
that reaches the line or character bound ends with `... (truncated)`.
`unattributedTotal` and `unattributed` are non-zero only when status is `incomplete`.

## Reading it

A rule spread thinly across every area is a habit; a rule concentrated in one directory is one
module's history. The first is a tightening decision, the second is an afternoon.
