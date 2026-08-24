# Quality

Maintained by [ebpy](https://github.com/yoshum/ebpy). Numbers are rendered from
`.ebpy/state.json`; edits outside the notes block are overwritten on the next run.

> **The diagnosis below is stale** — 289 commits since the diagnosis; re-run diagnose before trusting it.
> Numbers and file names may describe code that has since moved.

- Phase: **drain**
- Frozen: 2026-08-24T06:07:06Z
- Open violations: **212**
- Rules improved since the ceiling: **0**
- Analyzers: **mypy, ruff**

## Worklist

Top to bottom. An unattended run works this list and nothing else.

- [x] **P0 diagnose** — taken 2026-08-18T00:08:49Z
- [x] **P1 bootstrap** — nothing missing
- [x] **P2 freeze** — frozen 2026-08-24T06:07:06Z
- [ ] **P3 drain** — 212 findings across 12 rules
  - [ ] `ruff:PLC2801` — 1 left
  - [ ] `ruff:RUF027` — 1 left
  - [ ] `ruff:PLR2004` — 2 left
  - [ ] `ruff:PLC1901` — 3 left
  - [ ] `ruff:RUF105` — 6 left
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
| `ruff:D205` | 96 | 96 | 0 | draining |
| `ruff:PLR6301` | 33 | 33 | 0 | draining |
| `ruff:RUF067` | 21 | 21 | 0 | draining |
| `ruff:D401` | 19 | 19 | 0 | draining |
| `ruff:PLC2701` | 14 | 14 | 0 | draining |
| `ruff:ANN401` | 8 | 8 | 0 | draining |
| `ruff:SLF001` | 8 | 8 | 0 | draining |
| `ruff:RUF105` | 6 | 6 | 0 | draining |
| `ruff:PLC1901` | 3 | 3 | 0 | draining |
| `ruff:PLR2004` | 2 | 2 | 0 | draining |
| `ruff:PLC2801` | 1 | 1 | 0 | draining |
| `ruff:RUF027` | 1 | 1 | 0 | draining |

## Outstanding

### tighten

- [ ] **No dead-code detection** — vulture reports unused functions, classes and variables. Report-only at first; a counter later.

## Work log

| Date | Commit | Kind | Rule | What |
| --- | --- | --- | --- | --- |
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
| 2026-08-24 | 22fb31a3 | drained | ruff:D403 | 6 violations in test_diagnose.py and test_mypy_lifecycle.py; capitalized sentence-initial mypy/freeze; not a real bug, docstring wording |
| 2026-08-24 | 428adea6 | drained | ruff:ANN401 | 2 violations in repo/detect/tooling.py and store/baseline.py; Any -> object for isinstance-narrowed JSON inputs; not a real bug, tighter typing |
| 2026-08-24 | 844b88d6 | drained | ruff:PT018 | 7 violations across render/analysis_report.py and 3 test modules; split compound 'assert A and B' into separate asserts; not a real bug, clearer failure messages |
| 2026-08-24 | 414e9de1 | drained | ruff:TC002 | 1 violation in tests/test_report.py; moved type-only pytest import into TYPE_CHECKING block; not a real bug, mechanical typing fix |
| 2026-08-24 | 17c4efdc | drained | ruff:TC001 | 34 of 38 violations across 20 files; moved annotation-only first-party imports into TYPE_CHECKING blocks; not a bug — import hygiene; 4 left in commands/freeze.py (leave-until-last) |
| 2026-08-24 | 3cd6be2c | drained | ruff:D102 | 5 violations across 5 files (to_dict serializers, PinnedAction.uses, test bundle load); added method docstrings; not a bug — fully graduates |

## Notes

<!-- ebpy:notes:start -->
_Anything written between these markers survives a re-render._
<!-- ebpy:notes:end -->
