# Working on ebpy

ebpy is a Python port of [ever-better](https://github.com/isamu/ever-better). It makes an existing
codebase one that can **only get better**: record every violation that exists today as a ceiling,
then hold new code to the whole rule set while the ceiling falls and never rises.

## The division of labour

The CLI does what is deterministic — detect, install, count, render, gate. The skills do what needs
judgment — is this violation a real bug, is this duplication or coincidence, what deserves an issue.
Anything an agent would do slowly or differently on each run belongs in the CLI; anything a markdown
checklist cannot express belongs in a skill.

## Shape of the code

- `src/ebpy/models.py` — every shared value. Frozen dataclasses; `State` is the one mutable one.
- Decisions are **pure functions over facts**. `repo/` does the disk reading (`repo/facts.py`,
  `repo/git.py`, `repo/fan_in.py`, `repo/detect/`); `decide/` turns those facts into verdicts
  (`decide/diagnose.py`, `decide/analysis_report.py`, `decide/drain_order.py`,
  `decide/bootstrap_plan.py`, `decide/freshness.py`), and everything under `render/` turns a
  verdict into text. None of these touch the filesystem, so all are testable without one.
- `measurement/` is the toolchain seam. Ruff and mypy become one Measurement value before any
  command applies ratchet policy; the per-tool runners are `measurement/_ruff.py` and
  `measurement/_mypy.py`, private to the package. See `docs/measurement-seam.md`.
- `store/` owns the `.ebpy/` files: `store/baseline.py` the ratchet file, `store/state.py` the
  ledger, `store/ceiling_artifacts.py` the pair. Nothing outside `store/` writes either.
- Commands under `commands/` are thin: validate ceiling artifacts, gather, decide, render, persist.

## Rules that are not in the linter

- **Zero runtime dependencies.** The tool that gates a repository's dependencies does not add its
  own. Dev dependencies are fine.
- **A comment says why, never what.** If it restates the line below it, delete it. The comments
  worth keeping are the ones recording a decision the code cannot show — a measured behaviour of an
  external tool, a trap that cost somebody an afternoon.
- **Names measure claims.** `directory_tails` reports the last files *carrying* a rule; it does not
  claim the rest of the directory is clean, and the docstring says so. Do not widen a name past what
  the arithmetic supports.
- **Absence and zero are different.** "no warnings" and "nobody looked for warnings" must never
  render the same way, and a counter must never be written from a run that did not happen.
- **Tests are named as sentences.** `test_freeze_lowers_but_never_raises`, not `test_freeze_2`. The
  test name is where the rule lives.

## Before you push

```bash
uv run ruff format .
uv run ruff check .
uv run mypy .
uv run pytest
uv run ebpy check
```

The last one is this repository eating its own cooking: it fails if any count rose above its ceiling.
After fixing a grandfathered violation, run `uv run ebpy prune` and commit `.ebpy/baseline.json`
with the fix — that is the only way the ceiling comes down.
