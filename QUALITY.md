# Quality

Maintained by [ebpy](https://github.com/yoshum/ebpy). Numbers are rendered from
`.ebpy/state.json`; edits outside the notes block are overwritten on the next run.

> **The diagnosis below is stale** — 253 commits since the diagnosis; re-run diagnose before trusting it.
> Numbers and file names may describe code that has since moved.

- Phase: **drain**
- Frozen: 2026-08-24T06:07:06Z
- Open violations: **1151**
- Rules improved since the ceiling: **0**
- Analyzers: **mypy, ruff**

## Worklist

Top to bottom. An unattended run works this list and nothing else.

- [x] **P0 diagnose** — taken 2026-08-18T00:08:49Z
- [x] **P1 bootstrap** — nothing missing
- [x] **P2 freeze** — frozen 2026-08-24T06:07:06Z
- [ ] **P3 drain** — 1151 findings across 23 rules
  - [ ] `ruff:FURB118` — 1 left
  - [ ] `ruff:PLC2801` — 1 left
  - [ ] `ruff:RUF027` — 1 left
  - [ ] `ruff:PLR2004` — 2 left
  - [ ] `ruff:TC002` — 2 left
- [ ] **P4 tighten** — add the next rule tier, then freeze and drain again
- [ ] **P5 duplication and dead code** — report-only scans; extraction is judgment, not a threshold

## Ratchet

Ceiling is the count at the last freeze. It may fall and must never rise.

| Rule | Ceiling | Now | Change | Status |
| --- | ---: | ---: | ---: | --- |
| `ruff:D103` | 377 | 377 | 0 | draining |
| `ruff:TID252` | 340 | 340 | 0 | draining |
| `ruff:D205` | 96 | 96 | 0 | draining |
| `ruff:D209` | 95 | 95 | 0 | draining |
| `ruff:TC003` | 40 | 40 | 0 | draining |
| `ruff:D101` | 36 | 36 | 0 | draining |
| `ruff:PLR6301` | 33 | 33 | 0 | draining |
| `ruff:D100` | 21 | 21 | 0 | draining |
| `ruff:RUF067` | 21 | 21 | 0 | draining |
| `ruff:D401` | 19 | 19 | 0 | draining |
| `ruff:PLC2701` | 14 | 14 | 0 | draining |
| `ruff:D403` | 11 | 11 | 0 | draining |
| `ruff:ANN401` | 10 | 10 | 0 | draining |
| `ruff:PT018` | 10 | 10 | 0 | draining |
| `ruff:SLF001` | 8 | 8 | 0 | draining |
| `ruff:RUF105` | 6 | 6 | 0 | draining |
| `ruff:TC001` | 4 | 4 | 0 | draining |
| `ruff:PLC1901` | 3 | 3 | 0 | draining |
| `ruff:PLR2004` | 2 | 2 | 0 | draining |
| `ruff:TC002` | 2 | 2 | 0 | draining |
| `ruff:FURB118` | 1 | 1 | 0 | draining |
| `ruff:PLC2801` | 1 | 1 | 0 | draining |
| `ruff:RUF027` | 1 | 1 | 0 | draining |

## Outstanding

### tighten

- [ ] **No dead-code detection** — vulture reports unused functions, classes and variables. Report-only at first; a counter later.

## Work log

| Date | Commit | Kind | Rule | What |
| --- | --- | --- | --- | --- |
| 2026-08-24 | 17c4efdc | drained | ruff:TC001 | 34 of 38 violations across 20 files; moved annotation-only first-party imports into TYPE_CHECKING blocks; not a bug — import hygiene; 4 left in commands/freeze.py (leave-until-last) |
| 2026-08-24 | 3cd6be2c | drained | ruff:D102 | 5 violations across 5 files (to_dict serializers, PinnedAction.uses, test bundle load); added method docstrings; not a bug — fully graduates |
| 2026-08-24 | 1a630f96 | drained | ruff:D104 | 4 violations across 4 subpackage __init__ files; added package docstrings naming each responsibility; not a bug — fully graduates |
| 2026-08-24 | 808114ee | drained | ruff:FURB118 | 2 of 3 violations (status.py, worklist.py); replaced (count,name) lambda sort key with operator.itemgetter(1,0); not a bug — clarity; 1 left in store/state.py (leave-until-last) |
| 2026-08-24 | ebe95816 | drained | ruff:RUF201 | 10 violations in pyproject.toml; replaced rule codes with names in ruff ignore lists; not a bug — config readability, behaviour unchanged |
| 2026-08-24 | 8db9fb39 | drained | ruff:D107 | 1 violation; documented ToolError.__init__ in errors.py; not a bug, docstring-only, rule fully graduates for src/ebpy |
| 2026-08-24 | 47eeae33 | drained | ruff:D105 | 1 violation; documented AnalysisMeasurement.__post_init__ in models.py; not a bug, docstring-only, rule fully graduates for src/ebpy |
| 2026-08-24 | b0d17551 | drained | ruff:D301 | 1 violation; raw-stringed the Windows-path docstring in test_cell_key.py; not a bug, docstring-only, rule fully graduates |
| 2026-08-24 | 45e3fcd2 | drained | ruff:TC006 | 12 violations across install.py, skills_install.py, test_measurement.py; quoted cast() type expressions so they are not evaluated at runtime; not a real bug, pure type-level change, rule fully graduates |
| 2026-08-24 | 3c6eafd4 | drained | ruff:PLW0717 | 1 violation; split _swap_staged_bundle's try clause into _move_existing_aside and _move_staged_into_place; not a real bug, but the split preserves the partial-progress-for-rollback invariant and is now test-pinned |
| 2026-08-24 | 382bbee6 | drained | ruff:PLR0914 | 1 violation; extracted _prune_one_analyzer pure helper to drop prune_measurement below the local-variable ceiling; not a bug, a clean refactor with added test coverage |
| 2026-08-24 | 6ab6e121 | drained | ruff:PT011 | 4 violations in tests/test_cell_key.py; added match= to each pytest.raises(ValueError) so tests assert the specific guard message; not a real bug, a test-precision improvement |
| 2026-08-24 | 2da1cb12 | drained | ruff:PLR0916 | 1 violation in ruff/_runner.py; extracted _read_diagnostic pure function so per-field validation reads as guards instead of one 8-term boolean; behaviour-preserving refactor, not a real bug |
| 2026-08-24 | 134aefea | drained | ruff:PLR6201 | 1 violation; changed mypy exit-code membership test from a tuple to a set literal and added a characterization test; not a real bug, behaviour-preserving refactor |
| 2026-08-24 | 242261a3 | drained | ruff:FURB110 | 1 violation; replaced ternary notes fallback with 'or' in render/quality.py; not a bug, pure readability |
| 2026-08-24 | 22d97c8d | drained | ruff:FURB113 | 1 violation in render/report.py; _gap_lines now uses lines.extend((title,detail)) instead of two appends. Not a bug — mechanical simplification. Rule fully graduated from the baseline. |
| 2026-08-24 | e3e27b97 | drained | ruff:FURB162 | 1 violation in decide/freshness.py; removed the redundant .replace(Z,+00:00) since fromisoformat handles Z on py>=3.11. Added a test pinning Z-suffixed parsing. Not a bug — a mechanical simplification. Rule graduated. |
| 2026-08-24 | 8c5308dc | drained | ruff:PERF401 | 1 violation in catalog.py; extract_exports rebuilt as a list comprehension. Not a bug — a mechanical simplification. Rule fully graduated from the baseline. |
| 2026-08-18 | 8decde14 | note |  | ported ever-better to Python: ratchet, diagnose, freeze, drain |

## Notes

<!-- ebpy:notes:start -->
_Anything written between these markers survives a re-render._
<!-- ebpy:notes:end -->
