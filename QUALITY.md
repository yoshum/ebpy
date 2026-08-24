# Quality

Maintained by [ebpy](https://github.com/yoshum/ebpy). Numbers are rendered from
`.ebpy/state.json`; edits outside the notes block are overwritten on the next run.

> **The diagnosis below is stale** — 226 commits since the diagnosis; re-run diagnose before trusting it.
> Numbers and file names may describe code that has since moved.

- Phase: **drain**
- Frozen: 2026-08-24T06:07:06Z
- Open violations: **1228**
- Rules improved since the ceiling: **0**
- Analyzers: **mypy, ruff**

## Worklist

Top to bottom. An unattended run works this list and nothing else.

- [x] **P0 diagnose** — taken 2026-08-18T00:08:49Z
- [x] **P1 bootstrap** — nothing missing
- [x] **P2 freeze** — frozen 2026-08-24T06:07:06Z
- [ ] **P3 drain** — 1228 findings across 34 rules
  - [ ] `ruff:D105` — 1 left
  - [ ] `ruff:D107` — 1 left
  - [ ] `ruff:D301` — 1 left
  - [ ] `ruff:PLC2801` — 1 left
  - [ ] `ruff:PLR0914` — 1 left
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
| `ruff:TC001` | 38 | 38 | 0 | draining |
| `ruff:D101` | 36 | 36 | 0 | draining |
| `ruff:PLR6301` | 33 | 33 | 0 | draining |
| `ruff:D100` | 21 | 21 | 0 | draining |
| `ruff:RUF067` | 21 | 21 | 0 | draining |
| `ruff:D401` | 19 | 19 | 0 | draining |
| `ruff:PLC2701` | 14 | 14 | 0 | draining |
| `ruff:TC006` | 12 | 12 | 0 | draining |
| `ruff:D403` | 11 | 11 | 0 | draining |
| `ruff:ANN401` | 10 | 10 | 0 | draining |
| `ruff:PT018` | 10 | 10 | 0 | draining |
| `ruff:RUF201` | 10 | 10 | 0 | draining |
| `ruff:SLF001` | 8 | 8 | 0 | draining |
| `ruff:RUF105` | 6 | 6 | 0 | draining |
| `ruff:D102` | 5 | 5 | 0 | draining |
| `ruff:D104` | 4 | 4 | 0 | draining |
| `ruff:PT011` | 4 | 4 | 0 | draining |
| `ruff:FURB118` | 3 | 3 | 0 | draining |
| `ruff:PLC1901` | 3 | 3 | 0 | draining |
| `ruff:PLR2004` | 2 | 2 | 0 | draining |
| `ruff:TC002` | 2 | 2 | 0 | draining |
| `ruff:D105` | 1 | 1 | 0 | draining |
| `ruff:D107` | 1 | 1 | 0 | draining |
| `ruff:D301` | 1 | 1 | 0 | draining |
| `ruff:PLC2801` | 1 | 1 | 0 | draining |
| `ruff:PLR0914` | 1 | 1 | 0 | draining |
| `ruff:PLR0916` | 1 | 1 | 0 | draining |
| `ruff:PLW0717` | 1 | 1 | 0 | draining |
| `ruff:RUF027` | 1 | 1 | 0 | draining |

## Outstanding

### tighten

- [ ] **No dead-code detection** — vulture reports unused functions, classes and variables. Report-only at first; a counter later.

## Work log

| Date | Commit | Kind | Rule | What |
| --- | --- | --- | --- | --- |
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
