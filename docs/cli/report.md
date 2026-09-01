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
- per-analyzer status — complete, incomplete, unavailable, failed, no-runner, or scope-mismatch —
  and the details when a measurement could not be taken or the contract disagrees with this run's
  scope;
- how many files have findings, per analyzer.

Every in-scope analyzer is measured independently. If Ruff cannot run but mypy can, the report
still includes the mypy backlog alongside the last known Ruff ceiling. If an analyzer cannot run, the report names
why rather than rendering an unmeasured count as zero.

## It is not a quality gate

An analyzer being unavailable and the summary file being unwritable do not fail the report: it
renders the usable half of the answer and says what was not measured. Findings themselves never
change the exit code.

Invalid inputs are different. If the baseline and ledger are incomplete, malformed or inconsistent,
`report` exits 1 before measuring; treating unreadable or disagreeing ceiling data as an empty
backlog would be a false report. Restore both matching files, or replace the contract explicitly
with `freeze --force`.

An empty scope is refused the same way, but only when there is also nothing to fall back on: if no
analyzer applies (no declaration and no evidenced language, or a declaration naming none) and the
frozen contract is itself empty, there is no standing left to show, so `report` exits 1 rather than
rendering nothing. A scope *mismatch* — the frozen contract naming an analyzer this run's detected
or declared scope does not — is different again: `report` is the one command that does not refuse
on it. It renders the disagreement as that analyzer's `scope-mismatch` status instead, because a
mismatch is exactly what a reader ran `report` to see.
[`check`](check.md#the-contract-and-this-runs-scope-must-agree),
[`freeze`](freeze.md#when-nothing-applies) and
[`prune`](prune.md#the-contract-and-this-runs-scope-must-agree) are the commands that actually
refuse on scope.

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

The `analyzers` object has one entry per analyzer this run measured, plus every analyzer the
frozen contract names even when this run did not measure it — that second case is what
`no-runner` and `scope-mismatch` below exist to report:

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

Each field is explained by the observation behind it, not by the status label — a `Measured`
observation flagged `scope-mismatch` still reports real `findings` and can still carry
`unattributedTotal` above zero:

- `status` is one of `complete`, `incomplete`, `unavailable`, `failed`, `no-runner`, or
  `scope-mismatch`. The first four come straight from the seam (`docs/measurement-seam.md`);
  `no-runner` means the frozen contract names an analyzer this build has no runner for at all;
  `scope-mismatch` means this run's detected or declared scope disagrees with what the frozen
  contract holds for that analyzer (`report` renders the disagreement rather than refusing —
  see [`ebpy check`](check.md) and [`ebpy freeze`](freeze.md) for the commands that do refuse).
- `findings` is the attributed cell total, present whenever the observation is `Measured` —
  including a `Measured` observation marked `scope-mismatch` — and `null` for `unavailable`,
  `failed` or `no-runner`, which have no measurement to total.
- `filesWithFindings` follows `findings`: present for the same observations, `null` for the same
  reason.
- `failure` is the bounded multi-line detail, present exactly when the observation is
  `unavailable` or `failed`; `null` otherwise. A detail that reaches the line or character bound
  ends with `... (truncated)`.
- `unattributedTotal` and `unattributed` reflect the `Measured` observation's own unattributed
  findings — syntax errors and the like — whenever it is `Measured`, regardless of `status`. They
  are `0` and `[]` for `unavailable`, `failed` and `no-runner`.

## Reading it

A rule spread thinly across every area is a habit; a rule concentrated in one directory is one
module's history. The first is a tightening decision, the second is an afternoon.
