# CLI reference

One page per command. Everything here is deterministic: detect, install, count, render, gate. The
judgment half lives in the [skills](../skills.md).

| Command | Phase | What it is for | Writes |
| --- | --- | --- | --- |
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
prose — `bootstrap`, `freeze`, `prune`, `secrets`, `catalog`, `log` — accept the flag and ignore it.

## Exit codes

| Code | Meaning | Which commands |
| --- | --- | --- |
| 0 | success | all |
| 1 | the gate failed, or the command could not do its job | `check`, `log` (bad `--kind` or empty text), `secrets` (scan could not run), any command when Ruff is missing or fails |
| 2 | secrets found | `secrets` only |

Only `check` and `secrets` are gates. Everything else returns 0 whenever it ran, including
`report` — see [why a report must never change an exit code](report.md#it-is-never-a-gate).

## Running it

ebpy runs *your* Ruff, with *your* config, from *your* virtualenv, so the invocation matters:

```bash
uv run ebpy check      # inside the project's environment — what CI does

# a repository that does not have ebpy yet; <tag> is a version from the Releases page
uvx --from "git+https://github.com/yoshum/ebpy@<tag>" ebpy diagnose
```

ebpy is [not published to a package index](../../README.md#install), so a bare `uvx ebpy` resolves
nothing — it is installed from a released tag, or added to the repository as a dev dependency.

`diagnose` and `bootstrap` read configs rather than run tools, so the throwaway `uvx` form is enough
for them. `freeze`, `check`, `prune`, `next` and `report` need the repository's own Ruff and mypy on
the path.

## Where the numbers live

| File | Written by | Read by |
| --- | --- | --- |
| `.ebpy/baseline.json` | `freeze`, `prune` | `check`, `next`, `report` |
| `.ebpy/state.json` | `diagnose --write`, `freeze`, `check`, `prune`, `log` | `status`, `check`, `QUALITY.md` |
| `QUALITY.md` | every command that writes the ledger | humans |

Commit all three. See [Artifacts](../../README.md#artifacts).
