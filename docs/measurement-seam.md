# Measurement seam

`Measurement` is the value seam between a repository's toolchain and ebpy's ratchet decisions.
It exists so an analyzer's toolchain may change without teaching every command its executable
discovery, arguments, exit codes or output formats.

The seam owns measured facts. It does not own ceilings, gate policy or persistence.

## The value

`measure_repository(cwd, scope)` returns one frozen `Measurement`. `scope` is the analyzer names
this run measures — decided by the caller, never by the registry itself — and a name the scope
names but this build has no runner for is skipped rather than raised. There is no protocol,
adapter registry or plugin framework: callers need a value, and a second production
implementation does not yet exist.

Each analyzer in scope has exactly one observation:

```text
Measurement
└── analyzers
    ├── ruff:   Measured[AnalysisMeasurement] | Unavailable | Failed
    ├── mypy:   Measured[AnalysisMeasurement] | Unavailable | Failed
    └── clippy: Measured[AnalysisMeasurement] | Unavailable | Failed
```

There is no parallel status array. A value cannot simultaneously say that an analyzer failed and
carry a successful result for it. `Measured(cells={})` is distinct from `Unavailable` and `Failed`,
so a run that did not happen can never ratchet a cell to zero.

The variants carry the producing tool's name. They do not carry a tool version: a field that is
always `None` cannot say whether the version was unprobed or absent, and the seam exists precisely
to keep those two apart. It gets added when something actually probes for one.

A failure carries two readings of itself. `summary` is the single line a sentence or a table row can
hold; `detail` is everything the tool wrote, bounded but not flattened, and says so when it had to be
cut. Readers take whichever fits: `freeze` sets the summary inside a sentence, while `check`, a
`CommandError` and `report --json` carry the detail whole.

Keeping only one line at the seam would lose it for every reader at once, whereas a reader with room
for one line can always take the summary. The cost is not hypothetical: a broken `pyproject.toml` and
an unknown rule selector are different problems with different fixes, and one line of Ruff reports
both as `ruff check failed (exit 2)`.

Which line becomes the summary is the runner's decision, because only it knows its tool. mypy prints
a usage banner before the `mypy: error:` line that explains it; Ruff prints a bare `ruff failed`
before the `Cause:` lines that matter. A generic "first line" picks the wrong one for both.

## Stable vocabulary

The command layer sees ebpy concepts rather than tool output:

- file × rule cells, with rule IDs namespaced as `<analyzer>:<local-code>` (e.g. `ruff:F401`,
  `mypy:arg-type`);
- findings that cannot be attributed to a rule;
- files carrying findings;
- measured, unavailable or failed capabilities.

Ruff, mypy and clippy are the analyzers this build ships. Each carries a `language` (Ruff and mypy
are Python; clippy is Rust), which is what lets a caller project a repository's detected languages
onto the analyzer set instead of hardcoding one. Their runners own executable discovery, CLI
arguments, exit-code interpretation and parsing. `CellCounts` and `AnalysisMeasurement` live in
`models.py` because both measurement and ceiling modules share them; measurement does not import
the baseline persistence module.

## Independent capabilities

Every in-scope analyzer is attempted independently. One analyzer's failure does not skip another —
a Ruff failure does not skip mypy, a clippy failure does not skip either. This keeps Measurement a
snapshot of everything that could be measured instead of a trace of which subprocess happened to
run first.

Commands decide what partial success means:

| Command | Analyzer unavailable or failed | Analyzer incomplete (unattributed findings) |
| --- | --- | --- |
| `report` | renders the ceiling backlog and names the failure | renders the ceiling backlog and names the unattributed findings |
| `check` | fails — a frozen contract ceiling went unverified | fails — the measurement is not comparable to the ceiling |
| `freeze` | refuses and writes nothing — `--force` does not exclude it | refuses and writes nothing |
| `prune` | preserves that namespace without touching it | preserves that namespace without touching it |

`report --json` exposes per-analyzer status in the `analyzers` object. Each entry includes
`status` (`complete`, `incomplete`, `unavailable`, `failed`, `no-runner`, or `scope-mismatch`),
`findings`, `filesWithFindings`, `failure` (the bounded multi-line detail when unavailable or
failed, otherwise `null`), and `unattributedTotal` / `unattributed` samples whenever the
observation carries unattributed findings — which is not exclusive to `incomplete`: a `Measured`
observation flagged `scope-mismatch` still reports the unattributed findings it measured.
`no-runner` is `report`'s own name for `classify(None)` — a contract analyzer this build has no
runner for at all. `scope-mismatch` is `report`'s own widening of the seam's vocabulary: an
analyzer the frozen contract names but this run's detected or declared scope does not (see
"Command shape" below). A detail that reaches the line or character bound ends with
`... (truncated)`.

## Command shape

The ceiling contract and today's measurement are separate seams. Every gate command follows this
order:

```text
read and classify CeilingArtifacts
  → enforce the command's precondition
  → scope decision + reconciliation
  → measure_repository
  → pure decision over values
  → persist and render
```

The precondition stays first. An invalid or already-frozen contract must be refused before any tool
runs — with one deliberate exception: a global `freeze --force` is the recovery path for an invalid
pair, so it skips this refusal on purpose and proceeds straight to scope and measurement, discarding
the old contract rather than reading it. Measurement never reads or repairs `.ebpy/baseline.json` or
`.ebpy/state.json`.

Scope decision comes next, once the precondition has cleared: `scope_decision` reconciles what
`.ebpy/config.json` declares, what language detection finds, and what the frozen contract already
covers into one `ScopeDecision`. Its `to_measure` (or, for a global freeze, `global_freeze_scope`)
is the analyzer-name tuple `measure_repository` is actually called with — the seam itself never
sees the three authorities, only the names they agreed on (see `docs/cli/freeze.md`, `check.md`,
`prune.md` and `report.md` for what each command does with a disagreement between those three).

The public decision functions are the test surface:

- `report_from_measurement`
- `check_measurement`
- `build_global_freeze`
- `build_scoped_freeze`
- `prune_measurement`

Their shells gather filesystem facts, call one decision function and perform the returned writes.
Tests construct Measurement literals; the real-Ruff lifecycle test remains the integration test for
the adapter contract.

## Failure boundary

Known external failures become observations:

- executable not found → `Unavailable`;
- tool process failure → `Failed("execution-failed")`;
- output that does not match the known format → `Failed("invalid-output")`.

Unexpected programming errors are not converted into tool failures. They propagate normally.
Syntax errors reported by Ruff are successful measurement with unattributed findings, not a failed
tool run.

## What a failure does to each command

The seam reports; it does not decide. Each command applies its own policy to the same value.

| | `report` | `check` | `freeze` | `prune` |
| --- | --- | --- | --- | --- |
| analyzer failed, ceiling exists | names it and uses ceiling as fallback | refuses — frozen ceiling went unverified | refuses — `--force` does not exclude it | preserves namespace unchanged |
| analyzer failed, no ceiling | names it beside measurement note | passes, names what went unmeasured | refuses — every in-scope analyzer must be complete | no-op for that analyzer |
| analyzer incomplete | names unattributed samples and uses ceiling as fallback | refuses — measurement is not comparable to ceiling | refuses and writes nothing | preserves namespace unchanged |

`check` refuses on an unverified ceiling because a ceiling nobody could measure is not a ceiling
that held: a broken mypy would otherwise retire the type-error ratchet in silence, which is the
accumulation the ceiling exists to stop. Where no such ceiling exists there is nothing to verify,
so the gate passes — but it still names the capability it could not measure, because "no errors"
and "nobody ran" must never read the same.

A tool that cannot run is an ordinary command failure: the message goes to stdout and the exit
status is 1, the same as every other refusal. Before the seam, a missing Ruff was written to stderr
instead, so a script separating the two streams sees this move.
