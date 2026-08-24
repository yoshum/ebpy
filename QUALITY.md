# Quality

Maintained by [ebpy](https://github.com/yoshum/ebpy). Numbers are rendered from
`.ebpy/state.json`; edits outside the notes block are overwritten on the next run.

> **The diagnosis below is stale** — 306 commits since the diagnosis; re-run diagnose before trusting it.
> Numbers and file names may describe code that has since moved.

- Phase: **drain**
- Frozen: 2026-08-24T06:07:06Z
- Open violations: **0**
- Rules improved since the ceiling: **0**
- Analyzers: **mypy, ruff**

## Worklist

Top to bottom. An unattended run works this list and nothing else.

- [x] **P0 diagnose** — taken 2026-08-18T00:08:49Z
- [x] **P1 bootstrap** — nothing missing
- [x] **P2 freeze** — frozen 2026-08-24T06:07:06Z
- [x] **P3 drain** — backlog empty
- [ ] **P4 tighten** — add the next rule tier, then freeze and drain again
- [ ] **P5 duplication and dead code** — report-only scans; extraction is judgment, not a threshold

## Carried over

Refactors left undone, with the commit each was seen at. Re-check before acting on an old one.

- [ ] `ruff:TID252` — 340 across 47 files; whole-repo relative->absolute import migration reverses an established convention — owner decision, see #54  _(2026-08-24, 37613734)_
- [ ] `ruff:D103` — 377 across 66 files; many are sentence-named tests where a docstring is redundant per CLAUDE.md — owner decision on exempting tests/, see #55  _(2026-08-24, 37613734)_

## Ratchet

Ceiling is the count at the last freeze. It may fall and must never rise.

Nothing to grandfather — the freeze found no violations.

## Outstanding

### tighten

- [ ] **No dead-code detection** — vulture reports unused functions, classes and variables. Report-only at first; a counter later.

## Work log

| Date | Commit | Kind | Rule | What |
| --- | --- | --- | --- | --- |
| 2026-08-24 | 5f9fd84a | drained | ruff:RUF067 | 21 across tools/, tools/ruff/, tools/mypy/ __init__.py; moved implementations into named modules, __init__ now re-exports only. No behaviour change; rule graduated. |
| 2026-08-24 | 07f77499 | drained | ruff:RUF105 | 6 noqa:ARG002 removed; ARG002 moved to a src/ebpy/tools/** per-file-ignore (protocol methods). No behaviour change; rule graduated. |
| 2026-08-24 | e5aa3982 | drained | ruff:PLC1901 | 1 in store/state.py; frozen_at (already str-narrowed) != '' -> truthiness. tests' PLC1901 handled via config. No behaviour change. |
| 2026-08-24 | a13213a1 | drained | ruff:PLR2004 | 2 in store/state.py; extracted STATE_SCHEMA_VERSION and used it at the comparisons and the write. No behaviour change. |
| 2026-08-24 | 2c887a55 | drained | ruff:D401 | 2 test docstrings made imperative; rule graduated. |
| 2026-08-24 | 2c887a55 | drained | ruff:D205 | 74 test docstrings restructured to summary+body; rule graduated. |
| 2026-08-24 | 0812cd98 | drained | ruff:D401 | 17 src docstrings made imperative while keeping the why. No behaviour change. |
| 2026-08-24 | 0812cd98 | drained | ruff:D205 | 22 src docstrings restructured to summary+body. No behaviour change. |
| 2026-08-24 | f9179139 | drained | ruff:ANN401 | 8 Any annotations tightened: 6 JSON validators + _legacy_version to object (isinstance-narrowed), with_diagnosis to Diagnosis, test helper to Callable[[Path], AnalysisMeasurement]. None skipped; mypy clean. No bug. |
| 2026-08-24 | 61ad5b5e | drained | ruff:FURB118 | 1 lambda in store/state.py state_to_dict replaced with operator.itemgetter(0); same trivial item[0] pattern. Mechanical, no bug. |
| 2026-08-24 | 7d093cd5 | drained | ruff:D403 | 5 docstring first-word capitalizations in test_freeze.py and test_runners.py. Mechanical, no bug. |
| 2026-08-24 | 5d48102a | drained | ruff:PT018 | 3 compound asserts (freeze.py, test_freeze.py, test_runners.py) split into single-condition asserts. Mechanical, no bug. |
| 2026-08-24 | ce13d008 | drained | ruff:TC002 | 1 violation in test_check.py; type-only third-party (pytest) import guarded by TYPE_CHECKING. Mechanical, no bug. |
| 2026-08-24 | c549e499 | drained | ruff:TC001 | 4 violations in freeze.py; first-party type-only imports guarded by TYPE_CHECKING. Mechanical, no bug. |
| 2026-08-24 | c228771b | drained | ruff:TC003 | 20 violations across 17 test files, freeze.py and store/state.py; type-only stdlib imports moved behind TYPE_CHECKING. Mechanical, no behaviour change, no bug. |
| 2026-08-24 | e2a9e19e | drained | ruff:D103 | 72 src-side functions documented; tests exempted separately. No behaviour change; rule graduated. |
| 2026-08-24 | a86da30e | drained | ruff:TID252 | 340 across 47 files; migrated relative imports to absolute per #54. Mechanical, no behaviour change; rule graduated. |
| 2026-08-24 | 37613734 | deferred | ruff:D103 | 377 across 66 files; many are sentence-named tests where a docstring is redundant per CLAUDE.md — owner decision on exempting tests/, see #55 |
| 2026-08-24 | 37613734 | deferred | ruff:TID252 | 340 across 47 files; whole-repo relative->absolute import migration reverses an established convention — owner decision, see #54 |
| 2026-08-24 | 695de069 | drained | ruff:D101 | 36 classes across 16 files; added one-line docstrings to public dataclasses/value objects; no real bug |

## Notes

<!-- ebpy:notes:start -->
_Anything written between these markers survives a re-render._
<!-- ebpy:notes:end -->
