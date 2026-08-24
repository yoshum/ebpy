# Quality

Maintained by [ebpy](https://github.com/yoshum/ebpy). Numbers are rendered from
`.ebpy/state.json`; edits outside the notes block are overwritten on the next run.

> **The diagnosis below is stale** — 274 commits since the diagnosis; re-run diagnose before trusting it.
> Numbers and file names may describe code that has since moved.

- Phase: **drain**
- Frozen: 2026-08-24T06:07:06Z
- Open violations: **623**
- Rules improved since the ceiling: **0**
- Analyzers: **mypy, ruff**

## Worklist

Top to bottom. An unattended run works this list and nothing else.

- [x] **P0 diagnose** — taken 2026-08-18T00:08:49Z
- [x] **P1 bootstrap** — nothing missing
- [x] **P2 freeze** — frozen 2026-08-24T06:07:06Z
- [ ] **P3 drain** — 623 findings across 19 rules
  - [ ] `ruff:FURB118` — 1 left
  - [ ] `ruff:PLC2801` — 1 left
  - [ ] `ruff:RUF027` — 1 left
  - [ ] `ruff:TC002` — 1 left
  - [ ] `ruff:PLR2004` — 2 left
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
| `ruff:D103` | 377 | 377 | 0 | draining |
| `ruff:D205` | 96 | 96 | 0 | draining |
| `ruff:PLR6301` | 33 | 33 | 0 | draining |
| `ruff:RUF067` | 21 | 21 | 0 | draining |
| `ruff:TC003` | 20 | 20 | 0 | draining |
| `ruff:D401` | 19 | 19 | 0 | draining |
| `ruff:PLC2701` | 14 | 14 | 0 | draining |
| `ruff:ANN401` | 8 | 8 | 0 | draining |
| `ruff:SLF001` | 8 | 8 | 0 | draining |
| `ruff:RUF105` | 6 | 6 | 0 | draining |
| `ruff:D403` | 5 | 5 | 0 | draining |
| `ruff:TC001` | 4 | 4 | 0 | draining |
| `ruff:PLC1901` | 3 | 3 | 0 | draining |
| `ruff:PT018` | 3 | 3 | 0 | draining |
| `ruff:PLR2004` | 2 | 2 | 0 | draining |
| `ruff:FURB118` | 1 | 1 | 0 | draining |
| `ruff:PLC2801` | 1 | 1 | 0 | draining |
| `ruff:RUF027` | 1 | 1 | 0 | draining |
| `ruff:TC002` | 1 | 1 | 0 | draining |

## Outstanding

### tighten

- [ ] **No dead-code detection** — vulture reports unused functions, classes and variables. Report-only at first; a counter later.

## Work log

| Date | Commit | Kind | Rule | What |
| --- | --- | --- | --- | --- |
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
| 2026-08-24 | 1a630f96 | drained | ruff:D104 | 4 violations across 4 subpackage __init__ files; added package docstrings naming each responsibility; not a bug — fully graduates |
| 2026-08-24 | 808114ee | drained | ruff:FURB118 | 2 of 3 violations (status.py, worklist.py); replaced (count,name) lambda sort key with operator.itemgetter(1,0); not a bug — clarity; 1 left in store/state.py (leave-until-last) |
| 2026-08-24 | ebe95816 | drained | ruff:RUF201 | 10 violations in pyproject.toml; replaced rule codes with names in ruff ignore lists; not a bug — config readability, behaviour unchanged |
| 2026-08-24 | 8db9fb39 | drained | ruff:D107 | 1 violation; documented ToolError.__init__ in errors.py; not a bug, docstring-only, rule fully graduates for src/ebpy |
| 2026-08-24 | 47eeae33 | drained | ruff:D105 | 1 violation; documented AnalysisMeasurement.__post_init__ in models.py; not a bug, docstring-only, rule fully graduates for src/ebpy |
| 2026-08-24 | b0d17551 | drained | ruff:D301 | 1 violation; raw-stringed the Windows-path docstring in test_cell_key.py; not a bug, docstring-only, rule fully graduates |
| 2026-08-24 | 45e3fcd2 | drained | ruff:TC006 | 12 violations across install.py, skills_install.py, test_measurement.py; quoted cast() type expressions so they are not evaluated at runtime; not a real bug, pure type-level change, rule fully graduates |

## Notes

<!-- ebpy:notes:start -->
_Anything written between these markers survives a re-render._
<!-- ebpy:notes:end -->
