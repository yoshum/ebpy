# CLI reference

One page per command. Everything here is deterministic: detect, install, count, render, gate. The
judgment half lives in the [skills](../skills.md).

| Command | Phase | What it is for | Writes |
| --- | --- | --- | --- |
| [`install`](install.md) | setup | add ebpy and its matching Claude Code skills | dependency metadata, lockfile, `.claude/skills` |
| [`skills install`](skills-install.md) | setup | install the current ebpy package's bundled skills | `.claude/skills` |
| [`diagnose`](diagnose.md) | P0 | survey the repository and name every gap | only with `--write` |
| [`bootstrap`](bootstrap.md) | P1 | install the missing tooling, generate the configs | configs, workflows |
| [`freeze`](freeze.md) | P2 | pin today's violations as the ceiling | baseline, ledger, `QUALITY.md` |
| [`check`](check.md) | P2+ | the CI gate: fail if anything rose | ledger, `QUALITY.md` (unless `--no-write`) |
| [`next`](next.md) | P3 | what to drain first, and what each fix enforces | nothing |
| [`prune`](prune.md) | P3 | after a fix, lower the ceiling to what still exists | baseline, ledger, `QUALITY.md` |
| [`log`](log.md) | P3+ | record what happened, stamped with the commit | ledger, `QUALITY.md` |
| [`status`](status.md) | any | the current phase, backlog, and staleness | nothing |
| [`report`](report.md) | any | the backlog as a rule × area table, for CI | `$GITHUB_STEP_SUMMARY` if set |
| [`secrets`](secrets.md) | P1+ | scan history and working tree for credentials | nothing |
| [`catalog`](catalog.md) | P5 | list the helpers that already exist | `docs/shared-helpers.md` |

## Global options

Both are accepted before *and* after the subcommand, because after it is where anybody would type
them.

| Flag | Meaning |
| --- | --- |
| `--cwd PATH` | the repository to operate on (default: the current directory) |
| `--json` | machine-readable output, on the commands that support it |

`--json` is honoured by `diagnose`, `status`, `next` and `report`. The commands that only ever emit
prose — `install`, `skills install`, `bootstrap`, `freeze`, `prune`, `secrets`, `catalog`, `log` —
accept the flag and ignore it.

## Exit codes

| Code | Meaning | Which commands |
| --- | --- | --- |
| 0 | success | all |
| 1 | the gate failed, the command could not do its job, or the ceiling artifacts are invalid | `install`, `skills install`, `diagnose --write`, `freeze`, `prune`, `check`, `status`, `next`, `report`, `log`, `secrets`, or any command when Ruff is missing or fails |
| 2 | secrets found | `secrets` only |

Only `check` and `secrets` are quality gates. A refusal returns 1 so automation cannot mistake an
invalid or unchanged result for a valid one. `report` does not fail merely because Ruff or the job
summary is unavailable, but it does fail when the artifacts it would report are invalid.

## Ceiling artifact integrity

`.ebpy/baseline.json` and `.ebpy/state.json` are one contract. ebpy recognises only three states:

| State | Valid files | What commands do |
| --- | --- | --- |
| fresh | neither file, or a readable pre-freeze ledger with no ceiling data | `freeze` may pin the first ceiling |
| frozen | both files are readable, the ledger records a freeze, and its per-rule ceilings match the baseline | normal ratchet commands run |
| invalid | every other combination, including one missing file, malformed data, or disagreeing ceilings | commands that use the artifacts exit 1 before measuring or writing |

ebpy does not infer or reconstruct missing ceiling data. Restore both matching files from version
control, or run `ebpy freeze --force` to discard the old contract and pin a complete new one.

## Running it

ebpy runs *your* Ruff, with *your* config, from *your* virtualenv, so the invocation matters:

```bash
uv run ebpy check      # inside the project's environment — what CI does

# a repository that does not have ebpy yet
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install
```

ebpy is [not published to a package index](../../README.md#install), so a bare `uvx ebpy` resolves
nothing — invoke the bootstrap command from its Git source, then let `install` add an exact release
or Git ref to the project.

`diagnose` and `bootstrap` read configs rather than run tools, so the throwaway `uvx` form is enough
for them. `freeze`, `check`, `prune`, `next` and `report` need the repository's own in-scope
analyzers — Ruff and mypy for Python, clippy for Rust — on the path.

## Where the numbers live

| File | Written by | Read by |
| --- | --- | --- |
| `.ebpy/baseline.json` | `freeze`, `prune` | every command that reads or updates the ceiling contract |
| `.ebpy/state.json` | `diagnose --write`, `freeze`, `check`, `prune`, `log` | every command that reads or updates the ceiling contract, `QUALITY.md` |
| `QUALITY.md` | every command that writes the ledger | humans |

Commit all three. See [Artifacts](../../README.md#artifacts).
