# Quality

Maintained by [ebpy](https://github.com/yoshum/ebpy). Numbers are rendered from
`.ebpy/state.json`; edits outside the notes block are overwritten on the next run.

> **The diagnosis below is stale** — 298 commits since the diagnosis; re-run diagnose before trusting it.
> Numbers and file names may describe code that has since moved.

- Phase: **drain**
- Frozen: 2026-08-24T06:07:06Z
- Open violations: **52**
- Rules improved since the ceiling: **0**
- Analyzers: **mypy, ruff**

## Worklist

Top to bottom. An unattended run works this list and nothing else.

- [x] **P0 diagnose** — taken 2026-08-18T00:08:49Z
- [x] **P1 bootstrap** — nothing missing
- [x] **P2 freeze** — frozen 2026-08-24T06:07:06Z
- [ ] **P3 drain** — 52 findings across 5 rules
  - [ ] `ruff:PLC1901` — 3 left
  - [ ] `ruff:RUF105` — 6 left
  - [ ] `ruff:SLF001` — 8 left
  - [ ] `ruff:PLC2701` — 14 left
  - [ ] `ruff:RUF067` — 21 left
- [ ] **P4 tighten** — add the next rule tier, then freeze and drain again
- [ ] **P5 duplication and dead code** — report-only scans; extraction is judgment, not a threshold

## Carried over

Refactors left undone, with the commit each was seen at. Re-check before acting on an old one.

- [ ] `ruff:TID252` — 340 across 47 files; whole-repo relative->absolute import migration reverses an established convention — owner decision, see #54  _(2026-08-24, 37613734)_
- [ ] `ruff:D103` — 377 across 66 files; many are sentence-named tests where a docstring is redundant per CLAUDE.md — owner decision on exempting tests/, see #55  _(2026-08-24, 37613734)_

## Ratchet

Ceiling is the count at the last freeze. It may fall and must never rise.

| Rule | Ceiling | Now | Change | Status |
| --- | ---: | ---: | ---: | --- |
| `ruff:RUF067` | 21 | 21 | 0 | draining |
| `ruff:PLC2701` | 14 | 14 | 0 | draining |
| `ruff:SLF001` | 8 | 8 | 0 | draining |
| `ruff:RUF105` | 6 | 6 | 0 | draining |
| `ruff:PLC1901` | 3 | 3 | 0 | draining |

## Outstanding

### tighten

- [ ] **No dead-code detection** — vulture reports unused functions, classes and variables. Report-only at first; a counter later.

## Work log

| Date | Commit | Kind | Rule | What |
| --- | --- | --- | --- | --- |
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
| 2026-08-24 | 4c9332ec | drained | ruff:D100 | 21 files (20 test modules + errors.py); added one-line module docstrings; enforced convention, no real bug |
| 2026-08-24 | cbe92432 | drained | ruff:D209 | 95 violations across 30 files; moved multi-line docstring closing quotes to their own line via ruff --fix; no real bug (pure formatting) |
| 2026-08-24 | 75240937 | drained | ruff:TC003 | 20 violations across 18 src modules; moved type-only imports (Path, Iterable, Callable, Traversable) into TYPE_CHECKING blocks; not a real bug, mechanical import hygiene |

## Notes

<!-- ebpy:notes:start -->
_Anything written between these markers survives a re-render._
<!-- ebpy:notes:end -->
