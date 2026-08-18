# Measurement seam

`Measurement` is the value seam between a repository's toolchain and ebpy's ratchet decisions.
It exists so Ruff and mypy may change without teaching every command their executable discovery,
arguments, exit codes or output formats.

The seam owns measured facts. It does not own ceilings, gate policy or persistence.

## The value

`measure_repository(cwd)` returns one frozen `Measurement`. There is no protocol, adapter registry
or plugin framework: callers need a value, and a second production implementation does not yet
exist.

Each capability has exactly one observation:

```text
Measurement
├── lint: Measured[LintMeasurement] | Unavailable | Failed
└── counters
    └── mypy:errors: Measured[int] | Unavailable | Failed
```

There is no parallel status array. A value cannot simultaneously say that lint failed and carry a
successful lint result. `Measured(0)` is distinct from `Unavailable` and `Failed`, so a run that did
not happen can never ratchet a counter to zero.

The variants carry the producing tool's name. `Measured` and `Failed` have a place for a tool
version, but the initial implementation leaves it unset rather than spawning an extra `--version`
process for every command.

## Stable vocabulary

The command layer sees ebpy concepts rather than tool output:

- file × rule cells;
- findings that cannot be attributed to a rule;
- files carrying findings;
- named ratcheted counters;
- measured, unavailable or failed capabilities.

Ruff currently produces the lint observation. mypy currently produces `mypy:errors`. Their runners
own executable discovery, CLI arguments, exit-code interpretation and parsing. `CellCounts` and
`LintMeasurement` live in `models.py` because both measurement and ceiling modules share them;
measurement does not import the baseline persistence module.

## Independent capabilities

Ruff and mypy are attempted independently. A Ruff failure does not skip mypy. This keeps
Measurement a snapshot of everything that could be measured instead of a trace of which subprocess
happened to run first.

Commands decide what partial success means:

| Command | Lint unavailable or failed | mypy unavailable or failed |
| --- | --- | --- |
| `report` | render the ceiling backlog and name the lint failure | render any lint result and name why mypy was not measured |
| `check` | fail and persist nothing | continue without changing the existing counter |
| `freeze` | refuse and persist nothing | pin Ruff cells without creating a type-error ceiling |
| `prune` | refuse and persist nothing | lower Ruff cells without changing the existing counter |

`report --json` exposes the concise reasons as `lintFailure` and `mypyFailure`. Raw multi-line tool
output is not part of the report contract.

## Command shape

The ceiling contract and today's measurement are separate seams. Every gate command follows this
order:

```text
read and classify CeilingArtifacts
  → enforce the command's precondition
  → measure_repository
  → pure decision over values
  → persist and render
```

The precondition stays first. An invalid or already-frozen contract must be refused before any tool
runs. Measurement never reads or repairs `.ebpy/baseline.json` or `.ebpy/state.json`.

The public decision functions are the test surface:

- `report_from_measurement`
- `check_measurement`
- `freeze_measurement`
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

## Deferred extensions

Multiple lint providers will require a rule-ID namespace before their cells can share a ceiling.
That is deliberately deferred: changing existing Ruff identifiers would require a baseline
migration and is not necessary to establish the seam.

Atomic replacement of the baseline and ledger, and making `QUALITY.md` failure fully recoverable,
are also separate persistence changes. Measurement owns today's facts, not the ceiling transaction.
