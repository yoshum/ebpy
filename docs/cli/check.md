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
| a file holds more violations of a rule than its cell allows | the file and rule beyond the ceiling, plus the five worst |
| an analyzer ceiling could not be verified | which ceiling went unverified, and what the tool said |
| Ruff could not run | why, and `ebpy bootstrap` as the fix |
| Ruff could not parse a file | the syntax errors, named |
| there is no baseline at all | run `ebpy freeze` and commit the result |
| the baseline and ledger are incomplete, malformed or inconsistent | restore the matching pair, or deliberately replace it with `ebpy freeze --force` |
| the frozen contract and this run's detected or declared scope disagree | which analyzers are unfrozen, undeclared, or no longer evidenced, and how to reconcile |
| no analyzer applies here at all | nothing to measure — declare one in `.ebpy/config.json`, or run from the repository root |
| a Rust workspace clippy previously covered no longer compiles in the configuration ebpy measures | which workspace and packages dropped out of coverage, and both ways to recover |

## The ratchet is per file and per rule, for every analyzer

Stricter than a repo-wide total, deliberately: a new file has **no cell of its own**, so its first
violation fails even when that rule's repo-wide count is unchanged. Moving code into a new file does
not carry its grandfathering with it. This applies equally to Ruff findings and mypy findings — a
type error moving from one file to another fails `check` even when the total is unchanged.

## Excess is reported per file

When a count exceeds its ceiling, `check` names the file and the rule together with how many
findings are beyond it — the information needed to find and fix them:

```
src/service.py  mypy:arg-type  +2
src/new_file.py  ruff:F401  +1
```

## Syntax errors cannot pass by having no count

A file that does not parse is invisible to every rule, so it has nothing to compare against a
ceiling. Check refuses rather than reading that silence as clean.

## An unverified ceiling is not a ceiling that held

If the ledger holds a contract analyzer's ceiling and that analyzer cannot run — a bad config, a
missing stubs package, the tool uninstalled — the gate fails. It has no measurement to compare, and
passing would let a broken tool quietly retire the ratchet while every other check stayed green.

Where the ledger holds no contract for that analyzer there is nothing to verify, so that analyzer
does not block the gate. The gate still names which capability went unmeasured: "no errors" and
"nobody type-checked" are different facts and must not print the same.

Unverified analyzer counts are left exactly as the ledger had them. A run that did not measure never
writes a number.

## Partial success is preserved

Each contract analyzer is evaluated independently. When one analyzer exceeds its ceiling while
another is clean, the clean analyzer's progress is still written — the improvement is not discarded
because a sibling failed. The run still exits 1, but the next run starts from the recorded
improvement.

`--no-write` skips all writes regardless of outcome, for a read-only environment or a run you do
not want to leave a trace.

## A configured analyzer the contract does not hold

If ebpy knows an analyzer (it is in `ebpy`'s built-in list) but the contract was frozen before that
analyzer could be measured, `check` names it in the output as a note — not a gate failure. Use
`ebpy freeze --analyzer NAME` to add it to the contract once the toolchain is complete.

## The contract and this run's scope must agree

`check` reconciles three authorities before measuring: what `.ebpy/config.json` declares, what
language detection finds in the repository, and what the frozen contract already covers. Any
disagreement — an analyzer declared but not frozen, frozen but no longer declared, or frozen but no
longer evidenced by the repository's files — fails the gate outright, before any tool runs, and
names exactly what disagrees and how to reconcile it: freeze the missing analyzer, re-declare it, or
run `ebpy freeze --force` to accept the narrower contract deliberately. `report` renders the same
disagreement as a `scope-mismatch` status instead of refusing; `check` is stricter because a
contract nobody is verifying is exactly the accumulation the gate exists to stop.

If no analyzer applies at all — no declaration and no evidenced language, or a declaration that
names none — `check` fails the same way: there is nothing to gate, and gating nothing is not the
same as gating zero.

## A workspace clippy can no longer measure

If a Rust workspace clippy's contract previously covered no longer compiles in the configuration
ebpy measures — typically because it references items hidden behind a `cfg` — `check` fails and
names the workspace, its packages, and a sample of the cells that would otherwise go unverified.
Fix the `cfg` so the workspace compiles again, or run `ebpy freeze --force` to accept the narrower
contract deliberately; only a `freeze --force` may narrow what the contract covers, since `check`
itself never rewrites the contract. Until then this is a gate failure, not a note, because a
package silently dropping out of coverage is the accumulation the ratchet exists to stop.

## What it writes

By default it records what it observed into `.ebpy/state.json` and re-renders `QUALITY.md`, so the
numbers a human reads are the numbers CI last measured. `--no-write` skips that.

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
one case for a forced re-pin. Re-pin only the analyzer whose rule changed with
[`freeze --force --analyzer NAME`](freeze.md#freezing-twice-is-refused); a global `freeze --force`
rebaselines every namespace and would grandfather unrelated analyzers' new violations. Do not add
`# noqa`: a suppression comment is a ceiling that never drains and that nothing reports.
