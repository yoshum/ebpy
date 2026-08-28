# Clippy Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `ebpy freeze` pin Clippy warnings as a ceiling and `ebpy check` gate them, in Rust-only and Rust+Python repositories, without changing what ebpy does for existing Python repositories.

**Architecture:** Three moves, in order. (1) Measurement becomes *scoped*: `measure_repository(cwd, scope)` takes the analyzer set as a value, computed by a new pure `ScopeDecision` from three authorities — `.ebpy/config.json`, language detection, and the frozen roster. (2) A new `tools/clippy/` package asks `cargo metadata` for the workspace topology, runs `cargo clippy --workspace --message-format=json`, and turns the JSON stream into cells, unattributed findings, and *unmeasured scopes*. (3) The ledger grows `unmeasuredPackages` so a package that once contributed to the ceiling cannot silently stop being measured.

**Tech Stack:** Python 3.10+, stdlib only apart from the one conditional backport described below. `subprocess` via `ebpy.util.run`. **`ebpy._toml` for manifests, never `import tomllib` directly** — `tomllib` arrived in 3.11 and the floor is 3.10, so `ebpy/_toml.py` re-exports `loads` and `TOMLDecodeError` from `tomllib` or from `tomli`, whichever the interpreter has. pytest + monkeypatch for unit tests; real `cargo`/`rustc` for integration tests, skipped when `cargo clippy --version` does not succeed.

**Spec:** `docs/clippy-analyzer-spec.md` (Japanese; design document, committed alongside this plan on the feature branch)

---

## Global Constraints

Every task's requirements implicitly include this section.

- **Zero runtime dependencies.** `pyproject.toml`'s `dependencies` list does not grow. It is not empty: it carries `tomli>=2.0; python_version < "3.11"`, the one exception the file's own comment justifies — `tomli` is `tomllib` before `tomllib` existed, and it leaves the install the moment the floor reaches 3.11. Nothing in this plan adds a second entry. Dev dependencies are fine.
- **`docs/clippy-analyzer-spec.md` and this plan file are already committed** on this feature branch, and no task re-adds them. Every `git add` in this plan names files explicitly; never `git add -A`, `git add .`, or `git add docs/` — not to keep these two out of the tree, but so that a task's commit carries only the files that task changed.
- **A comment says why, never what.** Delete a comment that restates the line below it.
- **Names measure claims.** Do not widen a name past what its arithmetic supports.
- **Absence and zero are different.** "nobody looked" and "measured zero" must never render the same way, and a counter must never be written from a run that did not happen.
- **Tests are named as sentences.** `test_freeze_lowers_but_never_raises`, not `test_freeze_2`.
- **`Literal` type aliases, never `Enum`.** `Enum` appears 0 times in `src/`; `typing.get_args` appears 0 times.
- **Line length 110, `target-version = "py310"`, mypy `strict = true` over `src` and `tests`.** The CI matrix runs 3.10 through 3.14 on Linux, macOS and Windows, so no task may reach for a 3.11-only spelling — `tomllib`, `Self`, `StrEnum`, `datetime.UTC` — without the same version guard `ebpy/_toml.py` uses.
- **Supported Rust range: 1.79 (floor) through current stable.** Any behaviour justified by measurement must hold at both ends.
- **v1 measures exactly one build configuration:** default features, the running platform, no `--all-targets`. Code outside it is neither ceilinged nor gated.
- **Before every commit:** `uv run ruff format .` then `uv run pytest`. Before pushing, also `uv run ebpy check`. A raw `uv run ruff check .` / `uv run mypy .` is **not** a gate here — both report the whole grandfathered backlog as failure.
- **Commit messages follow Conventional Commits** (this repository's convention; `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, with an optional scope).

### Two deliberate deviations from the spec, decided here

1. **`ClippyUnavailableError` base class.** The spec's D-3 says "no new exception type is needed", meaning the three-layer shape (`NotFound` / `Failed` / `InvalidOutput`) that `tools/ruff/_runner.py:27-35` uses. But two distinct situations must both become `Unavailable`: cargo cannot be executed, and the repository resolved to zero Cargo workspaces. Naming the second one `ClippyNotFoundError` would be a claim the name cannot support (*Names measure claims*). So `ClippyUnavailableError` is the base, `ClippyNotFoundError` and `ClippyNoWorkspaceError` are its two subclasses, and the analyzer catches the base. The three-layer *shape* is preserved: one branch per observation kind.
2. **`parse_clippy_output` returns configuration mismatch as data, not an exception.** The spec fixes the parser's return type as `AnalysisMeasurement` and its raises as `ClippyInvalidOutputError | ClippyFailedError`. A workspace dropped for configuration mismatch (D-6) is neither: it returns `AnalysisMeasurement(cells={}, unmeasured=(UnmeasuredScope(...),))`. This is why the parser takes `workspace: RustWorkspace` — it is the only place that holds the member directories that scope needs.

---

## File Structure

**New files**

| Path | Responsibility |
| --- | --- |
| `src/ebpy/repo/detect/language.py` | Which languages a repository contains, from the file list alone. Never runs a subprocess. |
| `src/ebpy/decide/analyzer_scope.py` | `ScopeDecision`: the three authorities over the analyzer set, their reconciliation, and the messages when they disagree. |
| `src/ebpy/decide/unmeasured.py` | Whether this run's unmeasured packages narrow the frozen contract, and what to say when they do. |
| `src/ebpy/tools/clippy/__init__.py` | Package seam; re-exports `run_clippy_check` so tests can monkeypatch one name. |
| `src/ebpy/tools/clippy/_errors.py` | The four clippy error types. Leaf module — imports only `ebpy.errors`. |
| `src/ebpy/tools/clippy/_topology.py` | `RustWorkspace` / `RustTopology` and `rust_topology()`: asks `cargo metadata` where the workspaces are. |
| `src/ebpy/tools/clippy/_paths.py` | D-9: turning a reported diagnostic path into a cell key, a dropped generated file, or an unattributed finding. |
| `src/ebpy/tools/clippy/_parser.py` | D-6/D-7/D-8: one `cargo clippy` invocation's stdout into one `AnalysisMeasurement`. |
| `src/ebpy/tools/clippy/_runner.py` | Probe, invoke, aggregate across workspaces. |
| `src/ebpy/tools/clippy/analyzer.py` | `ClippyAnalyzer`: exceptions into observations. |
| `src/ebpy/tools/clippy/detector.py` | `ClippyDetector` / `ClippySetup`: clippy's *configuration*, never Rust's existence. |
| `tests/test_analyzer_scope.py` | `ScopeDecision` unit tests. |
| `tests/test_language_detect.py` | Language detection unit tests. |
| `tests/test_clippy_paths.py` | D-9 path attribution unit tests. |
| `tests/test_clippy_parser.py` | Parser unit tests over synthetic stdout. |
| `tests/test_clippy_topology.py` | Topology unit tests (fake `run`) plus real-cargo integration tests. |
| `tests/test_clippy_runner.py` | Probe/aggregation unit tests plus real-cargo integration tests. |
| `tests/test_unmeasured.py` | Regression fail-closed decision tests. |
| `tests/test_clippy_lifecycle.py` | Real-cargo end-to-end lifecycle (D-10). |
| `tests/test_clippy_ci_guard.py` | The one clippy test that must fail, not skip, when CI installed a toolchain (§5.3). |

**Modified files**

| Path | Change |
| --- | --- |
| `src/ebpy/models.py` | `Language`, `UnmeasuredScope`, `AnalysisMeasurement.unmeasured`, `State.unmeasured_packages`; widen `UnattributedFinding` docstring past "syntax error". |
| `src/ebpy/measurement/analyzer.py` | `Analyzer.language` property. |
| `src/ebpy/repo/detect/detector.py` | `ToolDetector.languages`, `ToolDetector.requires_repository_setup`. |
| `src/ebpy/repo/facts.py` | `cargo_manifests`, `clippy_config_paths`, `InvalidToml`. |
| `src/ebpy/tools/registry.py` | `measure_repository(cwd, scope)`; register `ClippyAnalyzer` and `ClippyDetector`. |
| `src/ebpy/tools/{ruff,mypy}/analyzer.py`, `tools/{ruff,mypy}/detector.py`, `tools/{gitleaks,pytest,ruff_format,vulture}.py` | `language` / `languages` / `requires_repository_setup`. |
| `src/ebpy/commands/{check,freeze,prune,report}.py` | Scope decision, precondition order, unmeasured fail-closed. |
| `src/ebpy/commands/{diagnose,bootstrap,catalog,next_command}.py` | Python-only guards; `languages` argument. |
| `src/ebpy/decide/{analysis_report,diagnose}.py` | `scope-mismatch`, backlog carry, language filtering, gap condition. |
| `src/ebpy/render/{analysis_report,report,quality}.py` | Banner conditions, `KeyError` fix, unratcheted marker from gaps. |
| `src/ebpy/store/{ceiling_artifacts,state}.py` | `reconcile_scope` retired; `unmeasuredPackages` read/write. |
| `src/ebpy/commands/log.py` | `RULE_HINT` gains a clippy example. |
| `.github/workflows/quality.yml` | A `clippy-analyzer` job pinning Rust 1.79 and stable (§5.3). |

---

## Task 1: `Language` and analyzer self-declaration

**Files:**
- Modify: `src/ebpy/models.py` (after the `Framework` alias, ~line 21)
- Modify: `src/ebpy/measurement/analyzer.py`
- Modify: `src/ebpy/tools/ruff/analyzer.py`, `src/ebpy/tools/mypy/analyzer.py`
- Test: `tests/test_tools.py` (modify `test_analyzer_protocol_exposes_name_noun_measure`, `test_registry_lists_ruff_and_mypy_with_valid_names`)

**Interfaces:**
- Produces: `ebpy.models.Language = Literal["python", "rust"]`; `Analyzer.language -> Language` (a read-only property on the Protocol, a plain dataclass field on the concrete analyzers).

- [ ] **Step 1: Write the failing test**

In `tests/test_tools.py`, replace `test_analyzer_protocol_exposes_name_noun_measure` and add a language test:

```python
def test_analyzer_protocol_exposes_name_noun_language_measure() -> None:
    """Analyzer Protocol declares exactly the name, noun, language, and measure members."""
    assert {m for m in dir(Analyzer) if not m.startswith("_")} == {"name", "noun", "language", "measure"}


def test_every_analyzer_declares_the_language_it_measures() -> None:
    """Each analyzer names its own language, which is intrinsic to the tool, not to a repository."""
    assert {a.name: a.language for a in ANALYZERS} == {"ruff": "python", "mypy": "python"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py -v`
Expected: FAIL — `AssertionError` on the member set, and `AttributeError: 'RuffAnalyzer' object has no attribute 'language'`.

- [ ] **Step 3: Add the type alias**

In `src/ebpy/models.py`, directly after `Framework = Literal["django", "fastapi", "flask", "none"]`:

```python
# Singular deliberately: all three analyzers measure exactly one language today, and widening
# to a tuple later is a change the type checker points at every call site. A member meaning
# "every language" must never be added — `Framework`'s "none" is an absence, but "any" would
# be a universal, and conflating the two is what "absence and zero are different" forbids.
Language = Literal["python", "rust"]
```

- [ ] **Step 4: Add the property to the Protocol**

In `src/ebpy/measurement/analyzer.py`, import `Language` under `TYPE_CHECKING` (`from ebpy.models import AnalysisMeasurement, Language`) and add between `noun` and `measure`:

```python
    @property
    def language(self) -> Language:
        """The language this analyzer measures — intrinsic to the tool, not to any repository."""
        ...
```

- [ ] **Step 5: Declare it on both analyzers**

In `src/ebpy/tools/ruff/analyzer.py`, extend the dataclass body:

```python
@dataclass(frozen=True)
class RuffAnalyzer:
    """ruff analyzer that owns the full observation-building try/except."""

    name: str = "ruff"
    noun: str = "Lint violations"
    language: Language = "python"
```

with `from ebpy.models import Language` added to the `TYPE_CHECKING` block — except that a dataclass field annotation is evaluated at runtime by `dataclasses`, so import `Language` at module scope instead:

```python
from ebpy.models import Language
```

Do the same in `src/ebpy/tools/mypy/analyzer.py` (`name: str = "mypy"`, `noun: str = "Type errors"`, `language: Language = "python"` — keep the existing `noun` value, whatever it is).

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_tools.py tests/test_measurement.py -v`
Expected: PASS

- [ ] **Step 7: Full suite and format**

Run: `uv run ruff format . && uv run pytest`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/ebpy/models.py src/ebpy/measurement/analyzer.py src/ebpy/tools/ruff/analyzer.py src/ebpy/tools/mypy/analyzer.py tests/test_tools.py && git commit -m "feat(measurement): have each analyzer name the language it measures"
```

---

## Task 2: Language detection from the repository's file list

**Files:**
- Create: `src/ebpy/repo/detect/language.py`
- Test: `tests/test_language_detect.py`

**Interfaces:**
- Consumes: `ebpy.models.Language` (Task 1); `ebpy.repo.facts.list_all_files(cwd) -> list[str]`.
- Produces:
  - `RepoLanguages` — frozen dataclass with `languages: frozenset[Language]`
  - `languages_from_files(all_files: Iterable[str]) -> RepoLanguages`
  - `detect_languages(cwd: Path) -> RepoLanguages`
  - `has_python(cwd: Path) -> bool`, `has_rust(cwd: Path) -> bool`

**Design notes the implementer must not lose:**
- Markers are deliberately **wide**. Narrow markers would silently drop a repository that ebpy gates today. `.ipynb` is included because `ruff check .` already walks notebooks; `.pyi` / `.pyw` because a stub-only repository is measured today.
- Rust is `Cargo.toml` at any depth, **excluding any path with a `target` segment**. This rule claims only "a segment named `target`" — not "the target directory in general".
- Nothing here runs a subprocess. `cargo` being absent must never stop ruff and mypy from being measured.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_language_detect.py`:

```python
"""Language detection: what a repository contains, read from its file list alone."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ebpy.repo.detect.language import detect_languages, has_python, has_rust, languages_from_files

if TYPE_CHECKING:
    from pathlib import Path


def test_a_repository_with_no_markers_detects_no_language() -> None:
    assert languages_from_files(["README.md", "LICENSE"]).languages == frozenset()


def test_a_python_source_file_at_any_depth_detects_python() -> None:
    assert languages_from_files(["src/pkg/mod.py"]).languages == frozenset({"python"})


def test_a_notebook_only_repository_detects_python() -> None:
    """ruff walks notebooks by default, so a notebook-only repository is measured today."""
    assert languages_from_files(["analysis/run.ipynb"]).languages == frozenset({"python"})


def test_a_stub_only_repository_detects_python() -> None:
    """A .pyi-only repository is measured today; a narrower marker set would silently drop it."""
    assert languages_from_files(["stubs/thing.pyi"]).languages == frozenset({"python"})


def test_a_lockfile_alone_detects_python() -> None:
    assert languages_from_files(["uv.lock"]).languages == frozenset({"python"})


def test_a_cargo_manifest_at_any_depth_detects_rust() -> None:
    assert languages_from_files(["crates/a/Cargo.toml"]).languages == frozenset({"rust"})


def test_a_manifest_under_a_target_segment_does_not_detect_rust() -> None:
    """`target` is cargo's build directory; a manifest cargo itself wrote there is not the project."""
    assert languages_from_files(["target/package/foo-0.1.0/Cargo.toml"]).languages == frozenset()


def test_a_mixed_repository_detects_both_languages() -> None:
    files = ["pyproject.toml", "rust/Cargo.toml"]
    assert languages_from_files(files).languages == frozenset({"python", "rust"})


def test_detect_languages_reads_the_working_tree(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    assert detect_languages(tmp_path).languages == frozenset({"python", "rust"})
    assert has_python(tmp_path)
    assert has_rust(tmp_path)


def test_has_python_is_false_in_a_rust_only_tree(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    assert not has_python(tmp_path)
    assert has_rust(tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_language_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ebpy.repo.detect.language'`

- [ ] **Step 3: Write the implementation**

Create `src/ebpy/repo/detect/language.py`:

```python
"""Which languages a repository contains, as a function of its file list.

Detection never runs a subprocess. A machine without cargo must still be able to measure
the Python half of a mixed repository, so cargo's absence is clippy's availability — not a
failure of language detection. Confirming where the Cargo workspaces actually are is the
clippy runner's job (`tools/clippy/_topology.py`), and that one can fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ebpy.repo.facts import list_all_files

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from ebpy.models import Language

# Deliberately wide. Too wide only means ruff and mypy report "nothing here"; too narrow
# means a repository ebpy gates today silently falls out of scope. `.ipynb` is here because
# `ruff check .` already walks notebooks, and `.pyi`/`.pyw` because today's unscoped
# `measure_repository` measures a stub-only repository.
_PYTHON_SUFFIXES = (".py", ".pyi", ".pyw", ".ipynb")

_PYTHON_NAMES = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Pipfile",
        "Pipfile.lock",
        "ruff.toml",
        ".ruff.toml",
        "mypy.ini",
        ".mypy.ini",
        "uv.lock",
        "poetry.lock",
        "pdm.lock",
    }
)

_CARGO_MANIFEST = "Cargo.toml"

# Excluded by path segment, not by prefix: the claim is "a segment named `target`", which is
# all the arithmetic supports. A repository that renamed its target directory keeps those
# manifests as candidates, and `cargo metadata` rejects or de-duplicates them later.
_RUST_EXCLUDED_SEGMENT = "target"


@dataclass(frozen=True)
class RepoLanguages:
    """The languages found in one repository."""

    languages: frozenset[Language]


def _is_python_marker(file: str) -> bool:
    name = PurePosixPath(file).name
    return (
        file.endswith(_PYTHON_SUFFIXES)
        or name in _PYTHON_NAMES
        or (name.startswith("requirements") and name.endswith(".txt"))
    )


def _is_rust_marker(file: str) -> bool:
    parts = PurePosixPath(file).parts
    return bool(parts) and parts[-1] == _CARGO_MANIFEST and _RUST_EXCLUDED_SEGMENT not in parts[:-1]


def languages_from_files(all_files: Iterable[str]) -> RepoLanguages:
    """Return the languages these files evidence. Pure: for callers that already listed the tree."""
    found: set[Language] = set()
    for file in all_files:
        if "python" not in found and _is_python_marker(file):
            found.add("python")
        if "rust" not in found and _is_rust_marker(file):
            found.add("rust")
    return RepoLanguages(languages=frozenset(found))


def detect_languages(cwd: Path) -> RepoLanguages:
    """Return the languages in the repository at cwd, for callers holding no RepoFacts."""
    return languages_from_files(list_all_files(cwd))


def has_python(cwd: Path) -> bool:
    """Report whether the repository at cwd contains Python."""
    return "python" in detect_languages(cwd).languages


def has_rust(cwd: Path) -> bool:
    """Report whether the repository at cwd contains Rust."""
    return "rust" in detect_languages(cwd).languages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_language_detect.py -v`
Expected: PASS

- [ ] **Step 5: Format and run the full suite**

Run: `uv run ruff format . && uv run pytest`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/ebpy/repo/detect/language.py tests/test_language_detect.py && git commit -m "feat(detect): read a repository's languages from its file list"
```

---

## Task 3: `ScopeDecision` — the three authorities over the analyzer set

**Files:**
- Create: `src/ebpy/decide/analyzer_scope.py`
- Test: `tests/test_analyzer_scope.py`

**Interfaces:**
- Consumes: `RepoLanguages` (Task 2); `Analyzer.language` (Task 1); `ebpy.store.config.EbpyConfig`; `ebpy.models.State`; `ebpy.tools.ANALYZERS`.
- Produces:
  - `ScopeDecision` (frozen) with `declared: frozenset[str] | None`, `detected_analyzers: frozenset[str]`, `frozen: frozenset[str]`, `registered_analyzers: frozenset[str]`
  - properties `to_measure -> tuple[str, ...]`, `global_freeze_scope -> tuple[str, ...]`, `scope_mismatches -> frozenset[str]`
  - `mismatch() -> str | None`
  - `scope_decision(config: EbpyConfig | None, languages: RepoLanguages, state: State) -> ScopeDecision`
  - `empty_scope_message(decision: ScopeDecision) -> str`

**The four rules, verbatim from the spec — an implementer who gets one wrong breaks a gate:**

1. `to_measure` = `declared` when it exists, else `detected_analyzers`. Sorted tuple on the way out; sets everywhere inside, because the projection comes out in registry order and `frozen_analyzers` comes out sorted, and comparing tuples would call the same set a mismatch.
2. `global_freeze_scope` = `declared` when it exists, else `detected_analyzers | frozen`. **The union is what stops a forced freeze from silently narrowing the contract when `Cargo.toml` disappears.**
3. Reconciliation runs **only when `frozen` is non-empty**. A fresh repository's `declared` becomes the contract untouched — that is the adoption path.
4. Asymmetric rules: config-declared demands **exact equality** (symmetric difference); detection-derived demands only `(frozen ∩ registered) ⊆ detected`. The `∩ registered` is what preserves `no-runner` for an analyzer this build has no runner for — two existing tests pin that (`tests/test_check.py:373`, `tests/test_freeze.py:350`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_analyzer_scope.py`:

```python
"""ScopeDecision: what gets measured, and when the three authorities disagree."""

from __future__ import annotations

from ebpy.decide.analyzer_scope import ScopeDecision, empty_scope_message, scope_decision
from ebpy.models import State
from ebpy.repo.detect.language import RepoLanguages
from ebpy.store.config import EbpyConfig

REGISTERED = frozenset({"ruff", "mypy", "clippy"})


def _decision(
    declared: frozenset[str] | None = None,
    detected: frozenset[str] = frozenset(),
    frozen: frozenset[str] = frozenset(),
) -> ScopeDecision:
    return ScopeDecision(
        declared=declared,
        detected_analyzers=detected,
        frozen=frozen,
        registered_analyzers=REGISTERED,
    )


def test_a_declared_set_is_what_gets_measured() -> None:
    assert _decision(declared=frozenset({"ruff"}), detected=frozenset({"ruff", "mypy"})).to_measure == (
        "ruff",
    )


def test_without_a_config_the_detected_set_is_what_gets_measured() -> None:
    assert _decision(detected=frozenset({"mypy", "ruff"})).to_measure == ("mypy", "ruff")


def test_a_fresh_repository_never_reports_a_mismatch() -> None:
    """Reconciling against an empty roster would make every declared analyzer a mismatch."""
    decision = _decision(declared=frozenset({"ruff", "mypy"}))
    assert decision.mismatch() is None
    assert decision.scope_mismatches == frozenset()


def test_a_declared_set_must_match_the_contract_in_both_directions() -> None:
    declared_not_frozen = _decision(declared=frozenset({"ruff", "mypy"}), frozen=frozenset({"ruff"}))
    frozen_not_declared = _decision(declared=frozenset({"ruff"}), frozen=frozenset({"ruff", "mypy"}))
    assert declared_not_frozen.scope_mismatches == frozenset({"mypy"})
    assert frozen_not_declared.scope_mismatches == frozenset({"mypy"})
    assert "mypy" in (declared_not_frozen.mismatch() or "")
    assert "mypy" in (frozen_not_declared.mismatch() or "")


def test_a_detected_set_is_reconciled_in_one_direction_only() -> None:
    """Detected-but-unfrozen is a diagnose gap, not an error; frozen-but-undetected fails closed."""
    unfrozen = _decision(detected=frozenset({"ruff", "mypy"}), frozen=frozenset({"ruff"}))
    undetected = _decision(detected=frozenset({"ruff"}), frozen=frozenset({"ruff", "clippy"}))
    assert unfrozen.mismatch() is None
    assert undetected.scope_mismatches == frozenset({"clippy"})


def test_an_unregistered_frozen_analyzer_stays_a_no_runner_case() -> None:
    """`pylint` in the contract must reach classify(None), not be renamed a scope mismatch."""
    decision = _decision(detected=frozenset({"ruff"}), frozen=frozenset({"ruff", "pylint"}))
    assert decision.scope_mismatches == frozenset()
    assert decision.mismatch() is None


def test_reconciliation_does_not_depend_on_ordering() -> None:
    """The projection comes out in registry order and the roster comes out sorted."""
    decision = _decision(detected=frozenset({"ruff", "mypy"}), frozen=frozenset({"mypy", "ruff"}))
    assert decision.mismatch() is None


def test_a_forced_freeze_without_a_config_keeps_the_existing_contract() -> None:
    """Deleting Cargo.toml must not drop clippy from the contract just because nothing declared it."""
    decision = _decision(detected=frozenset(), frozen=frozenset({"clippy"}))
    assert decision.to_measure == ()
    assert decision.global_freeze_scope == ("clippy",)


def test_a_declared_set_is_the_whole_freeze_scope() -> None:
    """Narrowing the config and forcing is the one deliberate way to shrink the contract."""
    decision = _decision(declared=frozenset({"ruff"}), frozen=frozenset({"ruff", "mypy"}))
    assert decision.global_freeze_scope == ("ruff",)


def test_scope_decision_projects_languages_onto_analyzer_names() -> None:
    state = State(frozen_analyzers=("ruff",))
    decision = scope_decision(None, RepoLanguages(frozenset({"python"})), state)
    assert "ruff" in decision.detected_analyzers
    assert "clippy" not in decision.detected_analyzers
    assert decision.frozen == frozenset({"ruff"})


def test_scope_decision_reads_the_declared_set_from_the_config() -> None:
    decision = scope_decision(
        EbpyConfig(analyzers=("mypy", "ruff")), RepoLanguages(frozenset({"python"})), State()
    )
    assert decision.declared == frozenset({"mypy", "ruff"})


def test_the_empty_scope_message_names_what_was_looked_for() -> None:
    message = empty_scope_message(_decision())
    assert "no analyzer" in message.lower()
    assert ".ebpy/config.json" in message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_analyzer_scope.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ebpy.decide.analyzer_scope'`

- [ ] **Step 3: Write the implementation**

Create `src/ebpy/decide/analyzer_scope.py`:

```python
"""Which analyzers this run measures, and what to say when the authorities disagree.

Three authorities have a claim on the set: `.ebpy/config.json` (what the repository declared),
language detection (what the repository contains), and the frozen roster (what the ceiling
already covers). Carrying them as three bare arguments is how a caller forgets one; carrying
them as one frozen value makes the reconciliation a method and the omission impossible.

`registered_analyzers` is not a fourth authority. It is this build's `ANALYZERS`, and it is
here for one job: keeping a contract analyzer this build has no runner for out of the
mismatch set, so it still reaches `classify(None)` and its one actionable message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ebpy.tools import ANALYZERS

if TYPE_CHECKING:
    from ebpy.models import State
    from ebpy.repo.detect.language import RepoLanguages
    from ebpy.store.config import EbpyConfig


@dataclass(frozen=True)
class ScopeDecision:
    """What three authorities say about the analyzer set, plus what this build can measure.

    All four are sets of **analyzer names**, never of languages. Sets and not tuples: the
    rules below are equality and containment, and comparing tuples would call the same set a
    mismatch because the projection comes out in registry order while `frozen_analyzers`
    comes out sorted. The one place a tuple appears is on the way out, where it is sorted.
    """

    declared: frozenset[str] | None
    detected_analyzers: frozenset[str]
    frozen: frozenset[str]
    registered_analyzers: frozenset[str]

    @property
    def to_measure(self) -> tuple[str, ...]:
        """The set this run actually measures: the declaration if there is one, else detection."""
        source = self.declared if self.declared is not None else self.detected_analyzers
        return tuple(sorted(source))

    @property
    def global_freeze_scope(self) -> tuple[str, ...]:
        """The set that becomes the new contract.

        Without a declaration the existing contract is unioned in, so a repository whose
        `Cargo.toml` went away cannot lose clippy from its contract by running `--force`.
        Narrowing the contract stays possible, but only by narrowing the declaration.
        """
        if self.declared is not None:
            return tuple(sorted(self.declared))
        return tuple(sorted(self.detected_analyzers | self.frozen))

    @property
    def scope_mismatches(self) -> frozenset[str]:
        """The analyzers the contract and this run's scope disagree about.

        Empty for a fresh repository: with no contract there is nothing to disagree with, and
        reconciling would make every declared analyzer a mismatch on the very first freeze.
        """
        if not self.frozen:
            return frozenset()
        if self.declared is not None:
            return self.declared ^ self.frozen
        return (self.frozen & self.registered_analyzers) - self.detected_analyzers

    def mismatch(self) -> str | None:
        """Explain a disagreement between the contract and this run's scope, or None if they agree."""
        mismatches = self.scope_mismatches
        if not mismatches:
            return None
        if self.declared is not None:
            unfrozen = sorted(self.declared - self.frozen)
            undeclared = sorted(self.frozen - self.declared)
            lines = [".ebpy/config.json and the frozen contract disagree on the analyzer set:"]
            if unfrozen:
                lines.append(
                    f"  declared but not frozen: {', '.join(unfrozen)}"
                    " — run `ebpy freeze --analyzer <name>`."
                )
            if undeclared:
                lines.append(
                    f"  frozen but not declared: {', '.join(undeclared)}"
                    " — re-declare it, or `ebpy freeze --force` to drop it."
                )
            return "\n".join(lines)
        return "\n".join(
            [
                "The frozen contract names analyzers this repository no longer evidences:",
                f"  {', '.join(sorted(mismatches))}",
                "Restore what they measure, declare the narrower set in .ebpy/config.json,",
                "or run `ebpy freeze --force` to accept the narrower contract deliberately.",
            ]
        )


def scope_decision(config: EbpyConfig | None, languages: RepoLanguages, state: State) -> ScopeDecision:
    """Assemble the three authorities into one value, projecting languages onto analyzer names.

    The projection lives here and nowhere else, so adding an analyzer keeps exactly one place
    to update — and so `frozen ⊆ detected_analyzers` cannot be misread as a set of languages.
    """
    detected = frozenset(a.name for a in ANALYZERS if a.language in languages.languages)
    return ScopeDecision(
        declared=frozenset(config.analyzers) if config is not None else None,
        detected_analyzers=detected,
        frozen=frozenset(state.frozen_analyzers),
        registered_analyzers=frozenset(a.name for a in ANALYZERS),
    )


def empty_scope_message(decision: ScopeDecision) -> str:
    """Explain a run with nothing to measure. Measuring nothing is not measuring zero."""
    source = "declares no analyzers" if decision.declared is not None else "evidences no supported language"
    return "\n".join(
        [
            f"No analyzer applies here: this repository {source}.",
            "Measuring nothing is not the same as measuring zero, so nothing was written.",
            "Declare the analyzers to ratchet in .ebpy/config.json, or run from the repository root.",
        ]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_analyzer_scope.py -v`
Expected: PASS (all clippy-related assertions still pass because `REGISTERED` in the test is a local literal, not the registry)

- [ ] **Step 5: Format and run the full suite**

Run: `uv run ruff format . && uv run pytest`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/ebpy/decide/analyzer_scope.py tests/test_analyzer_scope.py && git commit -m "feat(decide): fold the analyzer-set authorities into one ScopeDecision"
```

---

## Task 4: `measure_repository` takes a scope; `check` and `freeze` supply it

**Files:**
- Modify: `src/ebpy/tools/registry.py:76`
- Modify: `src/ebpy/commands/check.py` (imports; `run_check`)
- Modify: `src/ebpy/commands/freeze.py` (imports; `run_freeze`)
- Modify: `src/ebpy/store/ceiling_artifacts.py` (delete `reconcile_scope` and its now-unused `EbpyConfig` import)
- Test: `tests/test_measurement.py`, `tests/test_check.py`, `tests/test_freeze.py`, `tests/test_ceiling_artifacts.py`

**Interfaces:**
- Consumes: `ScopeDecision`, `scope_decision`, `empty_scope_message` (Task 3); `detect_languages` (Task 2).
- Produces: `measure_repository(cwd: Path, scope: tuple[str, ...]) -> Measurement`.

**Precondition order — per command, unchanged from today:**

| | order |
| --- | --- |
| `freeze` | config → artifacts → (global non-force: invalid/frozen refusals) → previous state → scope |
| `check` | artifacts → fresh short-circuit → config+scope → mismatch → empty scope |

`freeze --force` (global) is the **one** path that proceeds past invalid artifacts, because the invalid-artifacts message itself points at `--force` as the recovery. `freeze --analyzer` still refuses on invalid artifacts, with or without `--force`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_measurement.py`, every `measure_repository(tmp_path)` call becomes `measure_repository(tmp_path, ("ruff", "mypy"))` — except add these two new tests:

```python
def test_measure_repository_runs_only_the_analyzers_in_scope(tmp_path: Path) -> None:
    """Scope is a value the caller passes; the registry holds no policy about which apply."""
    result = measure_repository(tmp_path, ("ruff",))
    assert set(result.analyzers) == {"ruff"}


def test_measure_repository_ignores_a_scope_name_it_has_no_runner_for(tmp_path: Path) -> None:
    """A missing key is how `no-runner` is expressed; a KeyError would destroy that message."""
    result = measure_repository(tmp_path, ("ruff", "pylint"))
    assert set(result.analyzers) == {"ruff"}
```

In `tests/test_check.py` and `tests/test_freeze.py`, every stub `lambda _cwd: measurement` becomes `lambda _cwd, _scope: measurement` (and the equivalent for named stub functions). Then add to `tests/test_check.py`:

```python
def test_check_refuses_before_measuring_when_the_contract_names_an_undetected_analyzer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reconciling before measuring is what keeps a skipped analyzer from becoming `no-runner`."""
    _write_frozen_pair(tmp_path, frozen_analyzers=("ruff", "clippy"), cells={})

    def _never(_cwd: Path, _scope: tuple[str, ...]) -> Measurement:
        raise AssertionError("check must refuse before measuring")

    monkeypatch.setattr(check_command, "measure_repository", _never)
    result = check_command.run_check(tmp_path, write=False)
    assert not result.ok
    assert "clippy" in result.message
```

(`_write_frozen_pair` is the existing helper in that file; reuse whatever it is actually called there.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_measurement.py tests/test_check.py -v`
Expected: FAIL — `TypeError: measure_repository() takes 1 positional argument but 2 were given`

- [ ] **Step 3: Change the registry**

In `src/ebpy/tools/registry.py`, replace `measure_repository`:

```python
def measure_repository(cwd: Path, scope: tuple[str, ...]) -> Measurement:
    """Measure the analyzers named in ``scope``, retaining partial success as data.

    The registry holds no policy about which analyzers apply to a repository: `scope` arrives
    as a value from the caller that computed it. A name with no runner here is skipped rather
    than raised — that missing key is exactly how `classify(None)` reports "no runner in this
    build", and a KeyError would replace the one message a reader could act on.
    """
    return Measurement(
        analyzers={
            name: ANALYZERS_BY_NAME[name].measure(cwd) for name in scope if name in ANALYZERS_BY_NAME
        }
    )
```

`scope` is `tuple[str, ...]` and not a set because every caller already produces a sorted tuple; taking a set would let the output order vary between runs.

- [ ] **Step 4: Rewrite `run_check`**

In `src/ebpy/commands/check.py`, swap the `reconcile_scope` import for the scope decision:

```python
from ebpy.decide.analyzer_scope import empty_scope_message, scope_decision
from ebpy.repo.detect.language import detect_languages
from ebpy.store.ceiling_artifacts import invalid_artifacts_message, read_ceiling_artifacts
```

and replace the tail of `run_check`:

```python
    previous = artifacts.ledger.state
    assert previous is not None

    scope = scope_decision(read_config(cwd), detect_languages(cwd), previous)
    mismatch = scope.mismatch()
    if mismatch is not None:
        return CheckResult(ok=False, message=mismatch)
    if not scope.to_measure:
        return CheckResult(ok=False, message=empty_scope_message(scope))

    decision = check_measurement(previous, artifacts.cells, measure_repository(cwd, scope.to_measure))
```

- [ ] **Step 5: Rewrite `run_freeze`**

In `src/ebpy/commands/freeze.py`, add the imports and replace the scope computation. `ANALYZER_NAMES` is no longer used here — drop it from the import:

```python
from ebpy.decide.analyzer_scope import empty_scope_message, scope_decision
from ebpy.repo.detect.language import detect_languages
from ebpy.tools import measure_repository
```

```python
def run_freeze(cwd: Path, force: bool, analyzer: str | None) -> str:
    """Run ``ebpy freeze``: pin today's counts as the ceiling for one analyzer or the whole roster."""
    config = read_config(cwd)
    artifacts = read_ceiling_artifacts(cwd)

    if analyzer is not None:
        precondition_error = _check_scope_preconditions(artifacts, analyzer, force)
        if precondition_error is not None:
            raise CommandError(precondition_error)
    elif not force:
        if artifacts.kind == "invalid":
            raise CommandError(invalid_artifacts_message(artifacts))
        if artifacts.kind == "frozen":
            raise CommandError(_already_frozen(artifacts))

    previous = _previous_state(artifacts, force and analyzer is None)
    # The state a forced global recovery starts from, not the ledger as read: an invalid
    # ledger yields empty_state(), so a roster nobody could read cannot be resurrected into
    # the new contract and block the recovery a second time.
    scope = scope_decision(config, detect_languages(cwd), previous)
    frozen_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    if analyzer is not None:
        if analyzer not in scope.to_measure:
            in_scope = ", ".join(scope.to_measure) or "nothing"
            raise CommandError(
                f"{analyzer} is not in this repository's analyzer scope ({in_scope})."
                " Declare it in .ebpy/config.json, or check that what it measures is present here."
            )
        measurement = measure_repository(cwd, (analyzer,))
        decision = build_scoped_freeze(previous, artifacts.cells, measurement, analyzer, frozen_at)
    else:
        contract = scope.global_freeze_scope
        if not contract:
            raise CommandError(empty_scope_message(scope))
        # Measured with exactly the set that becomes the contract: measuring `to_measure` and
        # freezing `global_freeze_scope` would make an analyzer that was never run report
        # "no runner in this build", when the runner is right here.
        measurement = measure_repository(cwd, contract)
        decision = build_global_freeze(previous, measurement, force, frozen_at, list(contract))

    write_cells(cwd, decision.cells)
    write_state(cwd, decision.state)
    write_quality_file(cwd, decision.state)
    return decision.message
```

The old `config is not None and analyzer not in config.analyzers` check is **replaced**, not kept alongside: two rules cannot both hold when a config declares clippy in a repository with no `Cargo.toml`. `X ∈ to_measure` is the one that survives, because `to_measure` is where the config's override of detection already lives.

- [ ] **Step 6: Retire `reconcile_scope`**

Delete `reconcile_scope` from `src/ebpy/store/ceiling_artifacts.py` along with the `EbpyConfig` entry in its `TYPE_CHECKING` block. Delete its tests in `tests/test_ceiling_artifacts.py` — the same behaviour is now pinned by `test_a_declared_set_must_match_the_contract_in_both_directions` in `tests/test_analyzer_scope.py`.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 8: Format and commit**

```bash
git add src/ebpy/tools/registry.py src/ebpy/commands/check.py src/ebpy/commands/freeze.py src/ebpy/store/ceiling_artifacts.py tests/ && git commit -m "refactor(measurement): take the analyzer scope as an argument"
```

---

## Task 5: `prune` and `report` join the scope, and `report` never refuses for a mismatch

**Files:**
- Modify: `src/ebpy/commands/prune.py` (`run_prune`)
- Modify: `src/ebpy/commands/report.py` (`run_report`)
- Test: `tests/test_prune.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `scope_decision`, `empty_scope_message` (Task 3); `detect_languages` (Task 2).
- Produces: nothing new; both commands now call `measure_repository(cwd, scope.to_measure)`.

**The asymmetry to preserve:** `prune` touches the ceiling, so it refuses exactly where `check` refuses. `report` is the window you open *because* something is wrong, so it refuses only when its inputs are unreadable — never for a mismatch and never for an empty scope with a contract behind it.

| step | `prune` | `report` |
| --- | --- | --- |
| artifacts invalid | refuse | refuse |
| fresh | refuse (`NO_FROZEN_CEILING`) | proceed with `frozen_analyzers = ()` |
| scope mismatch | refuse | **proceed** (Task 6 renders it) |
| empty scope, fresh | n/a | refuse |
| empty scope, frozen | refuse | **proceed** |

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_report.py`:

```python
def test_report_does_not_refuse_when_the_contract_and_the_scope_disagree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """report is the window a reader opens because something is wrong; it stays open."""
    _write_frozen_pair(tmp_path, frozen_analyzers=("ruff", "clippy"), cells={})
    monkeypatch.setattr(report_command, "measure_repository", lambda _cwd, _scope: Measurement({}))
    output = report_command.run_report(tmp_path, as_json=False)
    assert "clippy" in output


def test_report_refuses_on_a_fresh_repository_with_nothing_to_measure(tmp_path: Path) -> None:
    """With no contract and no analyzer there is no standing for the report to show."""
    with pytest.raises(CommandError):
        report_command.run_report(tmp_path, as_json=False)
```

Add to `tests/test_prune.py`:

```python
def test_prune_refuses_before_measuring_when_the_scope_and_contract_disagree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prune lowers the ceiling, so it fails closed exactly where check does."""
    _write_frozen_pair(tmp_path, frozen_analyzers=("ruff", "clippy"), cells={})

    def _never(_cwd: Path, _scope: tuple[str, ...]) -> Measurement:
        raise AssertionError("prune must refuse before measuring")

    monkeypatch.setattr(prune_command, "measure_repository", _never)
    with pytest.raises(CommandError):
        prune_command.run_prune(tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_report.py tests/test_prune.py -v`
Expected: FAIL — `TypeError` on the two-argument stub, and no refusal from `prune`

- [ ] **Step 3: Wire `prune`**

In `src/ebpy/commands/prune.py`, add imports (`scope_decision`, `empty_scope_message`, `detect_languages`, `read_config`) and replace the tail of `run_prune`:

```python
    previous = artifacts.ledger.state
    assert previous is not None

    scope = scope_decision(read_config(cwd), detect_languages(cwd), previous)
    mismatch = scope.mismatch()
    if mismatch is not None:
        raise CommandError(mismatch)
    if not scope.to_measure:
        raise CommandError(empty_scope_message(scope))

    # Compare with the baseline file, not the ledger: check may already have lowered
    # the ledger's current values, which would make every prune look like a no-op.
    decision = prune_measurement(previous, artifacts.cells, measure_repository(cwd, scope.to_measure))
```

- [ ] **Step 4: Wire `report`**

In `src/ebpy/commands/report.py`, add the same imports plus `empty_state`, and replace the body from the freshness branch onward:

```python
    if artifacts.kind == "fresh":
        frozen_analyzers: tuple[str, ...] = ()
        previous = empty_state()
    else:
        state = artifacts.ledger.state
        assert state is not None
        frozen_analyzers = state.frozen_analyzers
        previous = state

    scope = scope_decision(read_config(cwd), detect_languages(cwd), previous)
    # A mismatch is what a reader ran `report` to see, so it is rendered rather than raised
    # (D-14). An empty scope only refuses when there is also no contract: with nothing
    # measured and nothing frozen there is no standing left to show.
    if not scope.to_measure and not frozen_analyzers:
        raise CommandError(empty_scope_message(scope))

    report = report_from_measurement(
        artifacts.cells,
        frozen_analyzers,
        measure_repository(cwd, scope.to_measure),
        scope.scope_mismatches,
    )
```

The fourth argument does not exist yet — Task 6 adds it. Until then, pass three arguments and add the fourth in Task 6. **Choose one:** implement Task 6's signature change here in the same commit, or land Task 5 with three arguments. This plan assumes the second; the line above is written for Task 6's shape so the diff in Task 6 is one word.

For this task, write it as:

```python
    report = report_from_measurement(
        artifacts.cells, frozen_analyzers, measure_repository(cwd, scope.to_measure)
    )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest -v`
Expected: PASS (the `scope-mismatch` *status* is not asserted yet; `test_report_does_not_refuse...` passes because clippy still appears as a contract analyzer row)

- [ ] **Step 6: Format and commit**

```bash
git add src/ebpy/commands/prune.py src/ebpy/commands/report.py tests/test_prune.py tests/test_report.py && git commit -m "feat(commands): give prune and report the same analyzer scope as check"
```

---

## Task 6: `report` names a scope mismatch as its own status

**Files:**
- Modify: `src/ebpy/decide/analysis_report.py` (`ReportAnalyzerStatus`, `AnalyzerSummary`, `_analyzer_summary`, `report_from_measurement`)
- Modify: `src/ebpy/render/analysis_report.py` (`_failure_banners`)
- Modify: `src/ebpy/commands/report.py` (pass `scope.scope_mismatches`)
- Test: `tests/test_analysis_report.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `ScopeDecision.scope_mismatches` (Task 3).
- Produces: `ReportAnalyzerStatus = AnalyzerStatus | Literal["scope-mismatch"]`; `report_from_measurement(baseline, frozen_analyzers, measurement, scope_mismatches)`.

**Two traps this task exists to avoid:**
1. `classify(None)` returns `"no-runner"`, whose documented meaning is *"a ledger contract naming an analyzer this ebpy build has no runner for at all"* (`measurement/observation.py:92`). Showing that for an analyzer that was merely skipped reports "no runner" when the runner is right there.
2. `_failure_banners` currently keys the unattributed banner on `summary.status == "incomplete"`. Once a status can be replaced by `scope-mismatch`, keying on the status hides the syntax-error banner from Markdown while `unattributedTotal` still sits in the JSON. **Key on the data the summary holds, not on the status.**

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_analysis_report.py`:

```python
def test_an_analyzer_outside_the_scope_is_a_scope_mismatch_not_a_missing_runner() -> None:
    """`no-runner` means this build ships no runner; saying it of a skipped analyzer is a lie."""
    report = report_from_measurement({}, ("ruff", "clippy"), Measurement({}), frozenset({"clippy"}))
    summaries = dict(report.analyzers)
    assert summaries["clippy"].status == "scope-mismatch"


def test_an_unregistered_contract_analyzer_is_still_a_missing_runner() -> None:
    report = report_from_measurement({}, ("pylint",), Measurement({}), frozenset())
    assert dict(report.analyzers)["pylint"].status == "no-runner"


def test_a_scope_mismatched_analyzer_keeps_its_failure_detail() -> None:
    """One status can only say one thing, but the detail is a separate fact worth keeping."""
    measurement = Measurement({"clippy": Failed(tool="clippy", failure_kind="execution-failed", detail="boom")})
    report = report_from_measurement({}, ("ruff",), measurement, frozenset({"clippy"}))
    summary = dict(report.analyzers)["clippy"]
    assert summary.status == "scope-mismatch"
    assert summary.failure == "boom"
```

Add to `tests/test_render.py` (or wherever `render_analysis_report` is exercised):

```python
def test_the_unparsed_file_banner_survives_a_scope_mismatch() -> None:
    """The banner keys on the unattributed findings themselves, not on a status that got replaced."""
    measurement = Measurement(
        {
            "clippy": Measured(
                tool="clippy",
                value=AnalysisMeasurement(
                    cells={}, unattributed=(UnattributedFinding(file="a.rs", line=1, message="x"),)
                ),
            )
        }
    )
    report = report_from_measurement({}, ("ruff",), measurement, frozenset({"clippy"}))
    assert "could not lint every file" in render_analysis_report(report)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_analysis_report.py tests/test_render.py -v`
Expected: FAIL — `TypeError: report_from_measurement() takes 3 positional arguments but 4 were given`

- [ ] **Step 3: Widen the status in the decide layer**

In `src/ebpy/decide/analysis_report.py`, add after the imports:

```python
# report's own widening of the seam's vocabulary. `AnalyzerStatus` itself is not widened:
# check, freeze and prune reconcile before measuring, so they never reach this state, and a
# value unreachable in the seam is a value every caller has to handle for nothing.
ReportAnalyzerStatus = AnalyzerStatus | Literal["scope-mismatch"]
```

Change `AnalyzerSummary.status` to `ReportAnalyzerStatus`, then thread the mismatch set:

```python
def _analyzer_summary(
    analyzer: str, in_contract: bool, measurement: Measurement, mismatched: bool
) -> AnalyzerSummary:
    observation = measurement.analyzers.get(analyzer)
    status: ReportAnalyzerStatus = "scope-mismatch" if mismatched else classify(observation)
    ...
```

leaving the rest of the function body as it is — including the `failure=detail` assignment, which is what keeps a `Failed` detail visible under a `scope-mismatch` status.

- [ ] **Step 4: Take the mismatch set as an argument**

```python
def report_from_measurement(
    baseline: CellCounts,
    frozen_analyzers: tuple[str, ...],
    measurement: Measurement,
    scope_mismatches: frozenset[str] = frozenset(),
) -> AnalysisReport:
    """Build a report from facts; tool failure changes its detail, never its exit status.

    `scope_mismatches` is computed by `ScopeDecision`, which is the only value that knows all
    three authorities. Deriving it here from `frozen - measurement.analyzers` would miss the
    config-declared-but-unfrozen direction entirely, since a declared analyzer is always
    measured.
    """
    contract_set = set(frozen_analyzers)
    all_analyzers = sorted(set(measurement.analyzers) | contract_set)

    analyzer_summaries = tuple(
        (a, _analyzer_summary(a, a in contract_set, measurement, a in scope_mismatches))
        for a in all_analyzers
    )
```

The roster stays `measurement.analyzers.keys() | frozen_analyzers`. Narrowing it to the measurement's keys would drop the `scope-mismatch` row and the ceiling numbers with it, for exactly the analyzer the reader opened the report to see. `declared` needs no explicit union: `measure_repository` keys the mapping on all of `to_measure`, and `declared ⊆ to_measure` by construction.

- [ ] **Step 5: Fix the renderer's banner condition**

In `src/ebpy/render/analysis_report.py`, in `_failure_banners`, replace `elif summary.status == "incomplete":` with:

```python
        elif summary.unattributed_total > 0:
```

- [ ] **Step 6: Pass the set from the command**

In `src/ebpy/commands/report.py`, add `scope.scope_mismatches` as the fourth argument to `report_from_measurement`.

- [ ] **Step 7: Run tests**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 8: Format and commit**

```bash
git add src/ebpy/decide/analysis_report.py src/ebpy/render/analysis_report.py src/ebpy/commands/report.py tests/ && git commit -m "feat(report): distinguish a scope mismatch from a missing runner"
```

---

**Stage #1 of the spec (§7) is complete at this point.** Existing Python repositories behave identically; the machinery clippy needs is in place and tested without clippy existing.

---

## Task 7: The clippy error types and `rust_topology`

**Files:**
- Create: `src/ebpy/tools/clippy/__init__.py`, `src/ebpy/tools/clippy/_errors.py`, `src/ebpy/tools/clippy/_topology.py`
- Modify: `src/ebpy/models.py` (add `UnmeasuredScope`, `AnalysisMeasurement.unmeasured`)
- Test: `tests/test_clippy_topology.py`

**Interfaces:**
- Consumes: `ebpy.util.run`, `ebpy.errors.ToolError`, `ebpy.repo.facts.list_all_files`.
- Produces:
  - `ClippyUnavailableError(ToolError)`, `ClippyNotFoundError(ClippyUnavailableError)`, `ClippyNoWorkspaceError(ClippyUnavailableError)`, `ClippyFailedError(ToolError)`, `ClippyInvalidOutputError(ClippyFailedError)`
  - `RustWorkspace(root: PurePosixPath, target_directory: Path, packages: tuple[str, ...])`
  - `RustTopology(workspaces: tuple[RustWorkspace, ...], unmeasured: tuple[UnmeasuredScope, ...])`
  - `rust_topology(cwd: Path) -> RustTopology`
  - `ebpy.models.UnmeasuredScope(root: str, packages: tuple[str, ...])`
  - `AnalysisMeasurement.unmeasured: tuple[UnmeasuredScope, ...] = ()`

**The discovery algorithm, which is the spec's normative pseudocode:**

```
candidates = every Cargo.toml in list_all_files(cwd) with no `target` path segment, sorted

for each still-unhandled candidate c:
    if `.cargo-checksum.json` sits beside it  ->  skip entirely (vendored; not "unmeasured")
    manifest = (cwd / c).resolve()                       # absolute, always
    [1] cwd = manifest.parent
        cargo metadata --no-deps --format-version 1 --manifest-path <manifest>
    [2] cwd = workspace_root
        cargo metadata --no-deps --format-version 1
    mark handled: c itself, workspace_root/Cargo.toml, every matched packages[].manifest_path
```

**Why each piece is there — do not simplify any of them away:**
- **Two invocations.** `--manifest-path` does not move the search base. rustup picks a toolchain from cwd, and cargo reads `.cargo/config.toml` hierarchically from cwd. One call from the repository root misses a nested workspace's pinned toolchain and `target-dir`. `[2]`'s `target_directory` is the one the measuring cwd will see, so `[2]` is what gets adopted.
- **No fallback when `[1]` fails.** A failure there means "which workspace this manifest belongs to could not be determined". Measuring anyway from some other cwd produces a measurement nobody can name the subject of.
- **Marking `c` itself and `workspace_root/Cargo.toml` handled.** A virtual workspace's root manifest has no `[package]`, so it appears in neither `workspace_members` nor `packages`. Marking only members leaves `c` unhandled (re-probed forever) — an actual infinite loop in a "repeat the first unhandled" implementation.
- **Per-member containment.** `workspace_root` being inside the repository does **not** imply its members are: a member whose own manifest carries `package.workspace = "../ws"` is accepted by cargo from outside the root, is genuinely linted, and is reported with an **absolute** path. D-9 would reject that path, but the diagnosis would say "clippy's output was unreadable" instead of naming the cause.
- **Package IDs are opaque.** Matched by exact equality inside the one metadata document. Never parsed.
- **Absolute manifest paths.** `list_all_files` returns repository-relative strings; combining `cwd = c.parent` with `--manifest-path c` makes cargo look for `crates/a/crates/a/Cargo.toml`.
- **`Path.resolve()` on both sides of every comparison,** including the repository root. Lexical comparison misreads a symlinked checkout and macOS's `/tmp` → `/private/tmp` as "outside the repository".
- **`target_directory` gets no containment check.** Cargo may legitimately place it outside the repository; what lands in a ceiling is a diagnostic path, not a build artifact location.
- **One failed candidate is dropped, not fatal.** A checked-in `vendor/` whose manifests are not excluded makes `cargo metadata` exit 101 for each of them while `cargo clippy --workspace` at the root exits 0. Failing the whole repository there means ebpy's own discovery manufactured the failure.
- **All candidates failing *is* fatal.** "Dropped everything" and "measured zero" must not be the same observation; `Measured(cells={})` there would let `prune` empty the ceiling.

- [ ] **Step 1: Add the new model values**

In `src/ebpy/models.py`, add above `AnalysisMeasurement`:

```python
@dataclass(frozen=True)
class UnmeasuredScope:
    """One range of a repository an analyzer could not measure, as the runner saw it.

    Two fields because the identity of the range and the identity of its container are
    different questions. `packages` is what the contract compares — a workspace root can stay
    the same while `members` and `exclude` move packages across it. `root` is what a message
    names, because "which workspace lost the ceiling" needs the container.
    """

    root: str
    packages: tuple[str, ...]
```

and extend `AnalysisMeasurement`:

```python
    # Syntax errors cannot be grandfathered: a file that does not parse is invisible
    # to every rule, so recording a rule count for it would be a lie.
    unattributed: tuple[UnattributedFinding, ...] = ()
    # Ranges this run did not measure at all. Distinct from an empty cell mapping, which
    # means the analyzer looked and found nothing.
    unmeasured: tuple[UnmeasuredScope, ...] = ()
```

Also widen `UnattributedFinding`'s docstring, since clippy's unplaceable paths are not syntax errors:

```python
@dataclass(frozen=True)
class UnattributedFinding:
    """A finding no cell can hold — typically a syntax error that hides a file from every rule.

    Not only syntax errors: any finding whose reported location cannot be placed in the
    ceiling's coordinate system lands here, such as a clippy diagnostic for a path outside
    the repository. The invariant is the same either way — a location the ratchet cannot
    key on cannot be grandfathered.
    """
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_clippy_topology.py`:

```python
"""Cargo workspace discovery: what cargo could and could not resolve in this repository."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from ebpy.tools.clippy import _topology
from ebpy.tools.clippy._errors import ClippyFailedError, ClippyInvalidOutputError, ClippyNotFoundError
from ebpy.tools.clippy._topology import rust_topology
from ebpy.util import ExecResult

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _metadata(root: Path, members: list[Path]) -> str:
    return json.dumps(
        {
            "workspace_root": str(root),
            "target_directory": str(root / "target"),
            "workspace_members": [f"path+file://{m}#0.1.0" for m in members],
            "packages": [
                {"id": f"path+file://{m}#0.1.0", "manifest_path": str(m / "Cargo.toml")} for m in members
            ],
        }
    )


def _fake_run(responses: dict[str, ExecResult]) -> Callable[[list[str], Path], ExecResult]:
    def _run(argv: list[str], cwd: Path) -> ExecResult:
        del argv
        return responses[str(cwd)]

    return _run


def test_a_single_package_repository_resolves_to_one_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    root = tmp_path.resolve()
    ok = ExecResult(code=0, stdout=_metadata(root, [root]), stderr="")
    monkeypatch.setattr(_topology, "run", _fake_run({str(root): ok}))
    topology = rust_topology(tmp_path)
    assert [w.root.as_posix() for w in topology.workspaces] == ["."]
    assert topology.workspaces[0].packages == (".",)
    assert topology.unmeasured == ()


def test_a_workspace_root_outside_the_repository_is_invalid_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository manifest can be a member of an outside workspace; that must be named, not measured."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    outside = tmp_path.parent.resolve() / "elsewhere"
    payload = _metadata(outside, [outside])
    monkeypatch.setattr(
        _topology, "run", lambda _argv, _cwd: ExecResult(code=0, stdout=payload, stderr="")
    )
    with pytest.raises(ClippyInvalidOutputError):
        rust_topology(tmp_path)


def test_a_member_outside_the_repository_is_invalid_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`package.workspace` lets cargo accept a member above the root; clippy then reports it absolute."""
    (tmp_path / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    root = tmp_path.resolve()
    outside = root.parent / "sibling"
    payload = _metadata(root, [outside])
    monkeypatch.setattr(
        _topology, "run", lambda _argv, _cwd: ExecResult(code=0, stdout=payload, stderr="")
    )
    with pytest.raises(ClippyInvalidOutputError):
        rust_topology(tmp_path)


def test_a_candidate_cargo_cannot_resolve_is_dropped_rather_than_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checked-in vendor/ makes metadata exit 101 while the repository itself builds fine."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    (tmp_path / "vendor" / "dep").mkdir(parents=True)
    (tmp_path / "vendor" / "dep" / "Cargo.toml").write_text("[package]\nname='d'\n", encoding="utf-8")
    root = tmp_path.resolve()
    ok = ExecResult(code=0, stdout=_metadata(root, [root]), stderr="")
    bad = ExecResult(code=101, stdout="", stderr="not in a workspace")
    monkeypatch.setattr(
        _topology, "run", _fake_run({str(root): ok, str(root / "vendor" / "dep"): bad})
    )
    topology = rust_topology(tmp_path)
    assert len(topology.workspaces) == 1
    assert [s.root for s in topology.unmeasured] == ["vendor/dep"]
    assert topology.unmeasured[0].packages == ("vendor/dep",)


def test_every_candidate_failing_is_a_failure_not_an_empty_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping everything must not become Measured(cells={}), which prune would act on."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    bad = ExecResult(code=101, stdout="", stderr="broken manifest")
    monkeypatch.setattr(_topology, "run", lambda _argv, _cwd: bad)
    with pytest.raises(ClippyFailedError):
        rust_topology(tmp_path)


def test_a_vendored_candidate_is_never_a_candidate_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A vendored dependency is not fixable code; giving it a ceiling would be pointless.

    It is skipped rather than recorded as unmeasured: recording it would grow the contract's
    set every time `cargo vendor` adds a dependency, and every growth reads as a regression.
    """
    (tmp_path / "Cargo.toml").write_text("[workspace]\nexclude=['vendor']\n", encoding="utf-8")
    dep = tmp_path / "vendor" / "cfg-if"
    dep.mkdir(parents=True)
    (dep / "Cargo.toml").write_text("[package]\nname='cfg-if'\n", encoding="utf-8")
    (dep / ".cargo-checksum.json").write_text("{}", encoding="utf-8")
    root = tmp_path.resolve()
    ok = ExecResult(code=0, stdout=_metadata(root, []), stderr="")
    monkeypatch.setattr(_topology, "run", _fake_run({str(root): ok}))
    topology = rust_topology(tmp_path)
    assert len(topology.workspaces) == 1
    assert topology.unmeasured == ()


def test_a_workspace_member_is_never_tested_for_the_vendor_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Members are already handled by the time the marker is consulted, so one cannot vanish."""
    (tmp_path / "Cargo.toml").write_text("[workspace]\nmembers=['a']\n", encoding="utf-8")
    member = tmp_path / "a"
    member.mkdir()
    (member / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    (member / ".cargo-checksum.json").write_text("{}", encoding="utf-8")
    root = tmp_path.resolve()
    ok = ExecResult(code=0, stdout=_metadata(root, [root / "a"]), stderr="")
    monkeypatch.setattr(_topology, "run", _fake_run({str(root): ok}))
    topology = rust_topology(tmp_path)
    assert topology.workspaces[0].packages == ("a",)


def test_a_missing_cargo_executable_is_reported_as_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")

    def _boom(_argv: list[str], _cwd: Path) -> ExecResult:
        raise FileNotFoundError("cargo")

    monkeypatch.setattr(_topology, "run", _boom)
    with pytest.raises(ClippyNotFoundError):
        rust_topology(tmp_path)


def test_unreadable_metadata_output_is_invalid_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful cargo whose output ebpy cannot read says nothing about the repository."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    monkeypatch.setattr(
        _topology, "run", lambda _argv, _cwd: ExecResult(code=0, stdout="not json", stderr="")
    )
    with pytest.raises(ClippyInvalidOutputError):
        rust_topology(tmp_path)


def test_a_repository_with_no_manifests_resolves_to_no_workspaces(tmp_path: Path) -> None:
    assert rust_topology(tmp_path).workspaces == ()
```

Add the real-cargo integration block at the bottom of the same file:

```python
def _clippy_available() -> bool:
    if shutil.which("cargo") is None:
        return False
    probe = subprocess.run(
        ["cargo", "clippy", "--version"], capture_output=True, text=True, check=False
    )
    return probe.returncode == 0 and probe.stdout.startswith("clippy ")


needs_clippy = pytest.mark.skipif(
    not _clippy_available(), reason="needs a toolchain whose `cargo clippy --version` succeeds"
)


@needs_clippy
def test_a_nested_manifest_resolves_against_real_cargo(tmp_path: Path) -> None:
    """The candidate must reach cargo absolute; relative would make it look for crates/a/crates/a."""
    (tmp_path / "Cargo.toml").write_text("[workspace]\nmembers=['crates/a']\n", encoding="utf-8")
    crate = tmp_path / "crates" / "a"
    (crate / "src").mkdir(parents=True)
    (crate / "Cargo.toml").write_text(
        "[package]\nname='a'\nversion='0.1.0'\nedition='2021'\n", encoding="utf-8"
    )
    (crate / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    topology = rust_topology(tmp_path)
    assert [w.root.as_posix() for w in topology.workspaces] == ["."]
    assert topology.workspaces[0].packages == ("crates/a",)


@needs_clippy
def test_a_virtual_workspace_root_is_marked_handled_and_not_probed_twice(tmp_path: Path) -> None:
    """A virtual root appears in neither workspace_members nor packages, so it needs marking."""
    (tmp_path / "Cargo.toml").write_text("[workspace]\nmembers=['a']\nresolver='2'\n", encoding="utf-8")
    crate = tmp_path / "a"
    (crate / "src").mkdir(parents=True)
    (crate / "Cargo.toml").write_text(
        "[package]\nname='a'\nversion='0.1.0'\nedition='2021'\n", encoding="utf-8"
    )
    (crate / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    topology = rust_topology(tmp_path)
    assert len(topology.workspaces) == 1


@needs_clippy
def test_an_excluded_package_is_found_as_its_own_workspace(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        "[workspace]\nmembers=['a']\nexclude=['side']\nresolver='2'\n", encoding="utf-8"
    )
    for name in ("a", "side"):
        crate = tmp_path / name
        (crate / "src").mkdir(parents=True)
        (crate / "Cargo.toml").write_text(
            f"[package]\nname='{name}'\nversion='0.1.0'\nedition='2021'\n", encoding="utf-8"
        )
        (crate / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    roots = {w.root.as_posix() for w in rust_topology(tmp_path).workspaces}
    assert roots == {".", "side"}


@needs_clippy
def test_a_checked_in_vendor_directory_does_not_make_the_repository_unmeasurable(tmp_path: Path) -> None:
    """`cargo metadata` exits 101 for a non-excluded vendored manifest; the root is still fine."""
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname='a'\nversion='0.1.0'\nedition='2021'\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    dep = tmp_path / "vendor" / "dep"
    (dep / "src").mkdir(parents=True)
    (dep / "Cargo.toml").write_text(
        "[package]\nname='dep'\nversion='0.1.0'\nedition='2021'\n", encoding="utf-8"
    )
    (dep / "src" / "lib.rs").write_text("pub fn g() {}\n", encoding="utf-8")
    topology = rust_topology(tmp_path)
    assert [w.root.as_posix() for w in topology.workspaces] == ["."]
    assert [s.root for s in topology.unmeasured] == ["vendor/dep"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_clippy_topology.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ebpy.tools.clippy'`

- [ ] **Step 4: Write the error types**

Create `src/ebpy/tools/clippy/_errors.py`:

```python
"""The failures clippy measurement can end in, one per observation the seam can hold.

Three layers, as ruff and mypy have: unavailable, failed, and failed-because-unreadable.
Unavailable has two subclasses rather than one because two genuinely different situations
end there — cargo cannot be executed, and cargo resolved no workspace at all — and calling
the second one "not found" would be a claim the name cannot support.
"""

from __future__ import annotations

from ebpy.errors import ToolError


class ClippyUnavailableError(ToolError):
    """clippy cannot measure this repository at all, so there is nothing to observe."""


class ClippyNotFoundError(ClippyUnavailableError):
    """cargo, or the clippy component, cannot be executed here."""


class ClippyNoWorkspaceError(ClippyUnavailableError):
    """cargo resolved no workspace in this repository, so clippy has nothing to run against."""


class ClippyFailedError(ToolError):
    """clippy ran and did not produce a usable measurement."""


class ClippyInvalidOutputError(ClippyFailedError):
    """clippy produced output ebpy could not read — a different fact from clippy failing."""
```

- [ ] **Step 5: Write the topology module**

Create `src/ebpy/tools/clippy/_topology.py`:

```python
"""Where the Cargo workspaces are, according to cargo itself.

Guessing from file layout does not work. Cargo searches parent directories for a
`[workspace]`, and `package.workspace` can name a root anywhere — so the outermost
`Cargo.toml` inside a repository can belong to a workspace outside it, whose other members
then get linted and reported relative to a root ebpy has never seen. `cargo metadata`
reports that situation correctly, which is the only reason it can be refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from ebpy.models import UnmeasuredScope
from ebpy.repo.facts import list_all_files
from ebpy.util import run

from ._errors import ClippyFailedError, ClippyInvalidOutputError, ClippyNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterator

_MANIFEST = "Cargo.toml"
_TARGET_SEGMENT = "target"
# cargo writes this beside every registry package it unpacks. It claims provenance — "this is
# cargo's copy of a published crate" — and nothing about whether the crate builds. A
# first-party package carrying this file would be dropped silently; that assumption is the
# price of not linting dependencies, and it is written down rather than hidden.
_VENDOR_MARKER = ".cargo-checksum.json"


@dataclass(frozen=True)
class RustWorkspace:
    """A Cargo workspace inside this repository, as cargo itself reports it."""

    # Repository-relative, always inside the repository. "." for a root workspace.
    root: PurePosixPath
    # Absolute, as cargo reported it. Deliberately not checked for containment: cargo may
    # legitimately place build output outside the repository, and what lands in a ceiling is
    # a diagnostic path, not an artifact location.
    target_directory: Path
    # Member package directories, repository-relative, ascending. Captured here because this
    # is the only moment they are knowable: the parser receives a RustWorkspace and a repo
    # root, and nothing downstream can reconstruct them.
    packages: tuple[str, ...]


@dataclass(frozen=True)
class RustTopology:
    """What cargo could and could not resolve in this repository."""

    workspaces: tuple[RustWorkspace, ...]
    unmeasured: tuple[UnmeasuredScope, ...]


def _candidates(cwd: Path) -> list[str]:
    return sorted(
        file
        for file in list_all_files(cwd)
        if (parts := PurePosixPath(file).parts)
        and parts[-1] == _MANIFEST
        and _TARGET_SEGMENT not in parts[:-1]
    )


def _relative(path: Path, repo_root: Path) -> str:
    return PurePosixPath(path.relative_to(repo_root)).as_posix()


def _inside(path: Path, repo_root: Path) -> bool:
    try:
        path.relative_to(repo_root)
    except ValueError:
        return False
    return True


def _metadata(cwd: Path, extra: list[str]) -> dict[str, Any]:
    argv = ["cargo", "metadata", "--no-deps", "--format-version", "1", *extra]
    try:
        result = run(argv, cwd)
    except OSError as error:
        raise ClippyNotFoundError(
            "cargo could not be executed",
            detail=f"cargo could not be executed: {error}",
        ) from error
    if result.code != 0:
        headline = f"cargo metadata failed (exit {result.code})"
        stderr = result.stderr.strip()
        raise ClippyFailedError(headline, detail=f"{headline}:\n{stderr}" if stderr else headline)
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ClippyInvalidOutputError(f"cargo metadata produced unparseable output: {error}") from error
    if not isinstance(raw, dict):
        raise ClippyInvalidOutputError("cargo metadata produced JSON of an unexpected shape")
    return raw


def _absolute_field(raw: dict[str, Any], key: str) -> Path:
    value = raw.get(key)
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ClippyInvalidOutputError(f"cargo metadata's {key} is not an absolute path")
    return Path(value)


def _member_manifests(raw: dict[str, Any]) -> Iterator[Path]:
    """Yield each workspace member's manifest, matching opaque package IDs by exact equality.

    The IDs are never parsed. The mapping closes inside this one document, so equality is
    all it takes, and a syntax the specification does not require ebpy to read is a syntax
    ebpy does not write a parser for.
    """
    members = raw.get("workspace_members")
    packages = raw.get("packages")
    if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
        raise ClippyInvalidOutputError("cargo metadata's workspace_members is not a list of strings")
    if not isinstance(packages, list):
        raise ClippyInvalidOutputError("cargo metadata's packages is not a list")
    by_id: dict[str, Path] = {}
    for package in packages:
        if not isinstance(package, dict):
            raise ClippyInvalidOutputError("cargo metadata reported a package of an unexpected shape")
        identifier = package.get("id")
        manifest = package.get("manifest_path")
        if not isinstance(identifier, str) or not isinstance(manifest, str):
            raise ClippyInvalidOutputError("cargo metadata reported a package without an id or manifest")
        if not Path(manifest).is_absolute():
            raise ClippyInvalidOutputError("cargo metadata reported a relative manifest_path")
        if identifier in by_id:
            raise ClippyInvalidOutputError(f"cargo metadata reported package id {identifier!r} twice")
        by_id[identifier] = Path(manifest)
    for member in members:
        if member not in by_id:
            raise ClippyInvalidOutputError(f"cargo metadata's member {member!r} matches no package")
        yield by_id[member]


def _resolve(manifest: Path, repo_root: Path) -> tuple[RustWorkspace, list[Path]]:
    """Resolve one candidate manifest into its workspace, plus the manifests now handled.

    Two invocations, because `--manifest-path` does not move the directory cargo and rustup
    search from: a nested workspace's `rust-toolchain.toml` and `.cargo/config.toml` are only
    seen from inside it. `[1]` answers "which workspace does this manifest belong to"; `[2]`
    re-reads from that root so the adopted `target_directory` is the one the measuring cwd
    will see. `[1]` failing is never retried from the root — resolving it there would produce
    a measurement whose subject nobody could name.
    """
    first = _metadata(manifest.parent, ["--manifest-path", str(manifest)])
    root = _absolute_field(first, "workspace_root").resolve()
    if not _inside(root, repo_root):
        raise ClippyInvalidOutputError(
            f"{_display(manifest, repo_root)} belongs to a Cargo workspace outside this repository"
        )
    second = _metadata(root, [])
    if _absolute_field(second, "workspace_root").resolve() != root:
        raise ClippyInvalidOutputError("cargo metadata reported two different workspace roots")

    member_manifests = [path.resolve() for path in _member_manifests(second)]
    for member in member_manifests:
        if not _inside(member, repo_root):
            raise ClippyInvalidOutputError(
                f"the workspace at {_relative(root, repo_root)} has a member outside this repository"
            )

    workspace = RustWorkspace(
        root=PurePosixPath(_relative(root, repo_root)),
        target_directory=_absolute_field(second, "target_directory"),
        packages=tuple(sorted(_relative(member.parent, repo_root) for member in member_manifests)),
    )
    # The candidate itself and the root manifest are marked alongside the members: a virtual
    # workspace's root has no [package], so it appears in neither workspace_members nor
    # packages, and marking members alone leaves it to be probed again forever.
    return workspace, [manifest, (root / _MANIFEST).resolve(), *member_manifests]


def _display(manifest: Path, repo_root: Path) -> str:
    return _relative(manifest, repo_root) if _inside(manifest, repo_root) else manifest.name


def rust_topology(cwd: Path) -> RustTopology:
    """Resolve this repository into the Cargo workspaces ebpy can measure.

    Candidates cargo cannot resolve are reported in `unmeasured` rather than raised, so one
    checked-in vendored manifest cannot make a healthy repository unmeasurable. Every
    candidate failing is still a failure: "dropped them all" and "measured zero" are
    different facts, and the second one would let `prune` empty the ceiling.

    Raises:
        ClippyNotFoundError: cargo cannot be executed.
        ClippyFailedError: no candidate resolved.
        ClippyInvalidOutputError: metadata output cannot be interpreted safely.
    """
    repo_root = cwd.resolve()
    workspaces: dict[str, RustWorkspace] = {}
    unmeasured: list[UnmeasuredScope] = []
    handled: set[Path] = set()
    first_failure: ClippyFailedError | None = None

    for candidate in _candidates(cwd):
        manifest = (cwd / candidate).resolve()
        if manifest in handled:
            continue
        # Consulted only for a candidate no workspace claimed: members are already handled by
        # now, so a first-party member carrying the marker cannot be dropped here.
        if (manifest.parent / _VENDOR_MARKER).is_file():
            handled.add(manifest)
            continue
        try:
            workspace, resolved = _resolve(manifest, repo_root)
        except ClippyInvalidOutputError:
            raise
        except ClippyFailedError as error:
            handled.add(manifest)
            directory = str(PurePosixPath(candidate).parent)
            unmeasured.append(UnmeasuredScope(root=directory, packages=(directory,)))
            first_failure = first_failure or error
            continue
        handled.update(resolved)
        workspaces.setdefault(workspace.root.as_posix(), workspace)

    if not workspaces and first_failure is not None:
        raise first_failure
    return RustTopology(
        workspaces=tuple(workspaces[key] for key in sorted(workspaces)),
        unmeasured=tuple(unmeasured),
    )
```

Note `str(PurePosixPath(candidate).parent)`: for a root `Cargo.toml` this yields `"."`, which is the same spelling `_relative` produces for the repository root — the two sets the contract compares must use one spelling.

- [ ] **Step 6: Write the package `__init__`**

Create `src/ebpy/tools/clippy/__init__.py`:

```python
"""clippy analyzer and detector: execution, observation, and configuration detection."""

from __future__ import annotations

from ._errors import (
    ClippyFailedError,
    ClippyInvalidOutputError,
    ClippyNoWorkspaceError,
    ClippyNotFoundError,
    ClippyUnavailableError,
)
from ._topology import RustTopology, RustWorkspace, rust_topology

__all__ = [
    "ClippyFailedError",
    "ClippyInvalidOutputError",
    "ClippyNoWorkspaceError",
    "ClippyNotFoundError",
    "ClippyUnavailableError",
    "RustTopology",
    "RustWorkspace",
    "rust_topology",
]
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_clippy_topology.py -v`
Expected: PASS (integration tests skip when no clippy toolchain is present)

- [ ] **Step 8: Format and commit**

```bash
git add src/ebpy/models.py src/ebpy/tools/clippy/ tests/test_clippy_topology.py && git commit -m "feat(clippy): resolve a repository into the Cargo workspaces cargo reports"
```

---

## Task 8: Turning a reported diagnostic path into a cell key

**Files:**
- Create: `src/ebpy/tools/clippy/_paths.py`
- Test: `tests/test_clippy_paths.py`

**Interfaces:**
- Consumes: `ebpy.cell_key.normalize_analyzer_path`; `ClippyInvalidOutputError` (Task 7).
- Produces:
  - `PathVerdict(kind: Literal["cell", "generated", "unattributed"], path: str = "")`
  - `attribute_path(reported: str, *, workspace_root: str, repo_root: Path, out_dirs: Sequence[str]) -> PathVerdict`
  - `normalize_out_dir(raw: str) -> str`

**Three outcomes, and never a fourth.** A path that cannot be placed is **not** `invalid-output`: the output was read fine, it just names a location the ceiling has no coordinate for. Every reason for that — UNC, drive-relative, a NUL byte, a symlink loop, a `--remap-path-prefix` target that does not exist — lands on the same conclusion. Do not add a branch per reason.

**The six steps, in order:**

1. `\` → `/`.
2. Decide absolute in **both** flavours, plus a bare Windows drive. `C:/outside/file.rs` is not absolute to `PurePosixPath`; `C:foo.rs` is not absolute to either, but has a drive. An absolute path under one of this invocation's `out_dir`s is **dropped silently** (generated code, not source); any other absolute path is unattributed.
3. Collapse the reported path **alone**, keeping a leading `..`. Empty, or a final segment of `..`, is unattributed.
4. Prefix the workspace root.
5. Collapse again, this time refusing a `..` that escapes. Escaping is unattributed.
6. Confirm a real file under the repository root, resolving both sides. `OSError`, `ValueError`, and `RuntimeError` are all caught here and all mean unattributed.

**Why two collapses.** One collapse after prefixing lets a path that names no file pass as a directory:

```
workspace_root = crates/a    reported = foo/..
  one pass : crates/a/foo/..  ->  crates/a     <- a directory becomes a cell key
  two pass : foo/..           ->  ""           <- refused at step 3
```

**Why step 6 exists.** `RUSTFLAGS=--remap-path-prefix=src=shadow` rewrites diagnostic paths textually and exits 0 with `success=true`. `shadow/lib.rs` looks repository-relative and passes steps 2–5. Without an existence check, cells for files that do not exist enter the ceiling.

**Why `out_dir` and not `target_directory`.** `build.build-dir` can put `OUT_DIR` outside the target directory (too narrow — real generated code becomes unattributed and freeze refuses forever); `CARGO_TARGET_DIR` can point at the repository root (too wide — every absolute path in the repository is discarded as "generated"). `out_dir` is cargo saying "I generated here", and misses in neither direction.

**Why the cell key stays lexical.** Containment and existence are checked against resolved paths, but what is written to the ceiling is the collapsed lexical path. Writing the resolved one makes a symlinked checkout produce a ceiling that does not reproduce.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_clippy_paths.py`:

```python
"""D-9: placing a reported clippy path in the ceiling's coordinate system, or refusing to."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ebpy.tools.clippy._errors import ClippyInvalidOutputError
from ebpy.tools.clippy._paths import attribute_path, normalize_out_dir

if TYPE_CHECKING:
    from pathlib import Path


def _place(tmp_path: Path, relative: str) -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("pub fn f() {}\n", encoding="utf-8")


def _verdict(tmp_path: Path, reported: str, root: str = "", out_dirs: tuple[str, ...] = ()) -> tuple[str, str]:
    result = attribute_path(reported, workspace_root=root, repo_root=tmp_path, out_dirs=out_dirs)
    return result.kind, result.path


def test_a_path_inside_the_repository_becomes_a_cell(tmp_path: Path) -> None:
    _place(tmp_path, "src/lib.rs")
    assert _verdict(tmp_path, "src/lib.rs") == ("cell", "src/lib.rs")


def test_the_workspace_root_is_prefixed_before_the_path_is_used(tmp_path: Path) -> None:
    """clippy reports relative to its workspace root, which is not the repository root."""
    _place(tmp_path, "crates/a/src/lib.rs")
    assert _verdict(tmp_path, "src/lib.rs", root="crates/a") == ("cell", "crates/a/src/lib.rs")


def test_a_parent_segment_that_stays_inside_the_repository_becomes_a_cell(tmp_path: Path) -> None:
    _place(tmp_path, "crates/shared/src/lib.rs")
    assert _verdict(tmp_path, "../shared/src/lib.rs", root="crates/a") == (
        "cell",
        "crates/shared/src/lib.rs",
    )


def test_a_leading_parent_segment_is_kept_until_the_root_is_prefixed(tmp_path: Path) -> None:
    """Refusing a leading `..` at step 3 would drop a legitimate `[lib] path = "../shared"`."""
    _place(tmp_path, "shared/src/lib.rs")
    assert _verdict(tmp_path, "../shared/src/lib.rs", root="crates") == ("cell", "shared/src/lib.rs")


def test_a_path_escaping_the_repository_is_unattributed(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "../../../etc/passwd.rs", root="crates/a")[0] == "unattributed"


def test_an_absolute_posix_path_is_unattributed(tmp_path: Path) -> None:
    """Absolute is the signal of a configuration ebpy does not measure; refusing is the diagnosis."""
    assert _verdict(tmp_path, "/etc/passwd.rs")[0] == "unattributed"


def test_a_windows_drive_path_is_unattributed(tmp_path: Path) -> None:
    """`C:/x.rs` is not absolute to PurePosixPath, so one flavour is not enough."""
    assert _verdict(tmp_path, "C:\\outside\\file.rs")[0] == "unattributed"


def test_a_drive_relative_path_is_unattributed(tmp_path: Path) -> None:
    """`C:foo.rs` is absolute in neither flavour; only the drive gives it away."""
    assert _verdict(tmp_path, "C:foo.rs")[0] == "unattributed"


def test_a_unc_path_is_unattributed(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "//server/share/x.rs")[0] == "unattributed"


def test_a_path_that_collapses_to_nothing_is_unattributed(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "foo/..")[0] == "unattributed"


def test_a_path_collapsing_to_nothing_under_a_nested_root_is_still_unattributed(tmp_path: Path) -> None:
    """One collapse after prefixing turns `foo/..` into the directory `crates/a`."""
    (tmp_path / "crates" / "a").mkdir(parents=True)
    assert _verdict(tmp_path, "foo/..", root="crates/a")[0] == "unattributed"


def test_a_path_that_names_no_file_is_unattributed(tmp_path: Path) -> None:
    for reported in ("..", "../foo/.."):
        assert _verdict(tmp_path, reported, root="crates/a")[0] == "unattributed"


def test_a_remapped_path_that_does_not_exist_is_unattributed(tmp_path: Path) -> None:
    """`--remap-path-prefix=src=shadow` rewrites the text and still exits 0 with success=true."""
    _place(tmp_path, "src/lib.rs")
    assert _verdict(tmp_path, "shadow/lib.rs")[0] == "unattributed"


def test_generated_code_under_a_reported_out_dir_is_dropped_silently(tmp_path: Path) -> None:
    """A build script's output is not source; unattributed would make freeze refuse forever."""
    out = "/build/x-abc/out"
    assert _verdict(tmp_path, f"{out}/gen.rs", out_dirs=(out,)) == ("generated", "")


def test_an_out_dir_match_respects_segment_boundaries(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "/build/outside.rs", out_dirs=("/build/out",))[0] == "unattributed"


def test_an_out_dir_is_normalized_before_it_is_compared() -> None:
    """Without this, a backslash-separated out_dir never matches a forward-slashed diagnostic."""
    assert normalize_out_dir("C:\\repo\\target\\debug\\build\\x\\out") == "C:/repo/target/debug/build/x/out"
    assert normalize_out_dir("/repo/target/./debug/../debug/build/x/out/") == (
        "/repo/target/debug/build/x/out"
    )


def test_a_relative_out_dir_is_invalid_output() -> None:
    """cargo documents out_dir as absolute; a relative one means ebpy is misreading the stream."""
    with pytest.raises(ClippyInvalidOutputError):
        normalize_out_dir("target/debug/build/x/out")


def test_a_path_that_resolves_outside_the_repository_is_unattributed(tmp_path: Path) -> None:
    """A ceiling keyed on this host's symlink resolution would not reproduce anywhere else."""
    outside = tmp_path.parent / "outside_target"
    outside.mkdir(exist_ok=True)
    (outside / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    assert _verdict(tmp_path, "link/lib.rs")[0] == "unattributed"


def test_a_nul_byte_in_a_path_is_unattributed_not_an_exception(tmp_path: Path) -> None:
    """clippy's output is external input; a raw ValueError must not escape the parser."""
    assert _verdict(tmp_path, "src/li\x00b.rs")[0] == "unattributed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_clippy_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ebpy.tools.clippy._paths'`

- [ ] **Step 3: Write the implementation**

Create `src/ebpy/tools/clippy/_paths.py`:

```python
"""Placing a reported clippy path in the ceiling's coordinate system, or refusing to.

Three outcomes and never a fourth: a cell, a generated file to drop, or a finding that
cannot be attributed. Every reason a path cannot be placed — a UNC share, a drive-relative
spelling, a NUL byte, a symlink loop, a `--remap-path-prefix` target that does not exist —
reaches the same conclusion, because the ratchet's question is only ever "can this be a
coordinate", never "why not".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Literal

from ebpy.cell_key import normalize_analyzer_path

from ._errors import ClippyInvalidOutputError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


@dataclass(frozen=True)
class PathVerdict:
    """Where a reported diagnostic path goes: a cell, the generated-code bin, or unattributed."""

    kind: Literal["cell", "generated", "unattributed"]
    path: str = ""


_UNATTRIBUTED = PathVerdict("unattributed")
_GENERATED = PathVerdict("generated")


def _is_absolute(path: str) -> bool:
    """Judge absoluteness in both flavours, plus a bare drive.

    `C:/outside/file.rs` is not absolute to PurePosixPath, so one flavour would prefix it
    with the workspace root and let it pass as repository-relative. `C:foo.rs` is absolute
    in neither, and only its drive gives it away.
    """
    return (
        PurePosixPath(path).is_absolute()
        or PureWindowsPath(path).is_absolute()
        or bool(PureWindowsPath(path).drive)
    )


def _collapse(path: str, *, keep_leading_parent: bool) -> str | None:
    """Fold `.` and `..` lexically, never by resolving. None means a `..` escaped.

    Lexical because resolving depends on this host's symlinks, and a ceiling keyed on that
    would not reproduce on another machine. `PurePosixPath` will not do it — Python keeps
    `..` deliberately.
    """
    stack: list[str] = []
    for part in path.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif keep_leading_parent:
                stack.append("..")
            else:
                return None
            continue
        stack.append(part)
    return "/".join(stack)


def normalize_out_dir(raw: str) -> str:
    """Normalize a reported `out_dir` into the spelling a diagnostic path can be compared against."""
    slashed = raw.replace("\\", "/")
    if not _is_absolute(slashed):
        raise ClippyInvalidOutputError(f"cargo reported a relative build-script out_dir: {raw!r}")
    drive = PureWindowsPath(slashed).drive
    rest = slashed[len(drive) :]
    rooted = rest.startswith("/")
    body = _collapse(rest, keep_leading_parent=True) or ""
    return f"{drive}{'/' if rooted else ''}{body}".rstrip("/")


def _under_out_dir(path: str, out_dirs: Sequence[str]) -> bool:
    candidate = path.rstrip("/")
    return any(candidate == out or candidate.startswith(f"{out}/") for out in out_dirs)


def _is_repository_file(repo_root: Path, relative: str) -> bool:
    """Confirm the path names a real file that resolves inside the repository.

    Without this, `--remap-path-prefix=src=shadow` — which rewrites diagnostic paths textually
    while still exiting 0 with `success=true` — puts cells for files that do not exist into
    the ceiling. Every filesystem error is an answer of "no": clippy's output is external
    input, and the parser's contract is that only its two error types leave it.
    """
    try:
        root = repo_root.resolve()
        candidate = (root / relative).resolve()
        if not candidate.is_file():
            return False
        candidate.relative_to(root)
    except (OSError, ValueError, RuntimeError):
        return False
    return True


def attribute_path(
    reported: str, *, workspace_root: str, repo_root: Path, out_dirs: Sequence[str]
) -> PathVerdict:
    """Decide where one reported diagnostic path belongs.

    `workspace_root` is repository-relative and comes from `cargo metadata`, not from the
    candidate manifest's directory: clippy reports relative to the workspace root, and those
    two differ for every nested workspace.
    """
    slashed = reported.replace("\\", "/")
    if _is_absolute(slashed):
        return _GENERATED if _under_out_dir(slashed, out_dirs) else _UNATTRIBUTED

    collapsed = _collapse(slashed, keep_leading_parent=True)
    # Emptiness alone is not enough: `..` and `../foo/..` both collapse to `..`, and prefixing
    # `crates/a` onto that yields the directory `crates`, which would become a cell key.
    if not collapsed or collapsed.split("/")[-1] == "..":
        return _UNATTRIBUTED

    prefixed = f"{workspace_root}/{collapsed}" if workspace_root not in ("", ".") else collapsed
    final = _collapse(prefixed, keep_leading_parent=False)
    if not final or not _is_repository_file(repo_root, final):
        return _UNATTRIBUTED
    return PathVerdict("cell", normalize_analyzer_path(final, repo_root))
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_clippy_paths.py -v`
Expected: PASS

- [ ] **Step 5: Format and commit**

```bash
git add src/ebpy/tools/clippy/_paths.py tests/test_clippy_paths.py && git commit -m "feat(clippy): place reported diagnostic paths in the ceiling's coordinates"
```

---

## Task 9: `parse_clippy_output`

**Files:**
- Create: `src/ebpy/tools/clippy/_parser.py`
- Test: `tests/test_clippy_parser.py`

**Interfaces:**
- Consumes: `RustWorkspace` (Task 7); `attribute_path`, `normalize_out_dir` (Task 8); `qualify_rule`; `UnmeasuredScope`, `AnalysisMeasurement`, `UnattributedFinding`.
- Produces: `parse_clippy_output(stdout: str, stderr: str, returncode: int, *, workspace: RustWorkspace, repo_root: Path) -> AnalysisMeasurement`

**One invocation, one call.** Never concatenate two workspaces' stdout: "exactly one `build-finished`" is an invariant of a single `cargo clippy` run.

**The five-step verdict — the order is the specification:**

```
1. a `{`-prefixed line that is not a readable JSON object,
   or a field below whose type is wrong          ->  invalid-output
2. no interpretable JSON object at all           ->  execution-failed
3. build-finished count is not exactly 1         ->  invalid-output
4. build-finished.success is false OR exit != 0  ->  configuration mismatch, or execution-failed
5. otherwise                                     ->  Measured
```

- **1 before everything** because nothing can be concluded from output that cannot be read — not even from a `success: true` found beside a broken line.
- **2 before 3** because "cargo died saying nothing" (zero output) and "cargo spoke but never finished" (partial output) are different facts: the first is the tool failing, the second is ebpy failing to read it.
- Line test is `line.startswith("{")` — **not** `lstrip()`. Cargo's own documented workaround for procedural-macro output on stdout is exactly this, and being lenient only blurs the boundary.

**The staged type checks. Read what is read; check only that.**

```
1. reason                                   str, required
2. compiler-message: message dict, level str
3. message.rendered kept per level as a failure-detail candidate (skip if not str)
4. level == "error": harvest `has_span` and `configured_out` LENIENTLY, then stop.
   Any other non-warning level: stop reading it entirely.
5. warning: code must be None or dict; None stops it
6. spans must be a list
7. each span must be a dict; is_primary must be a bool (absent = False)
8. at least one primary span, else stop
9. primary span only: file_name non-empty str; line_start/column_start positive int
10. only now: message.code.code non-empty str with no \r or \n
```

- **Step 3 before step 4** because a failed build's detail must quote the compiler errors. Discarding non-warnings early leaves nothing to quote.
- **Step 4's two facts are read but never type-checked.** They are consulted only after failure is certain, so strictness there would *downgrade* a real `execution-failed` into `invalid-output`; and an unreadable value falls to `False`, which means "real failure", which means the workspace is not dropped. The safe direction is automatic.
- **An unknown `level` stops at step 4** and its `code`/`spans` are never checked. rustc documents that enumerated fields may gain values; demanding types inside an unknown level lets a future rustc turn a measurement into `invalid-output`.
- **`message.code.code` is checked last** because a message with no primary span is discarded anyway, and checking a value that is never read makes a run fail for nothing.
- **The `\r`/`\n` rejection is not decoration.** `cell_key.qualify_rule` raises `ValueError` on those, and a bare `ValueError` escaping breaks the parser's contract. Wrap `qualify_rule`'s `ValueError` in `ClippyInvalidOutputError` as a second belt.
- **`build-finished.success` must be strictly `bool`.** `0`, `1`, `"true"` are all rejected.
- **`line_start` excludes `bool`.** `isinstance(True, int)` is true, so `true` would pass as line 1. Use `type(x) is int`.
- **`{"reason": "future-cargo-message"}` is ignored, not rejected.** Unreadable and unknown are different; only fields ebpy actually reads can make output invalid.

**Failure detail, in this order:** error-level `rendered` joined in stdout order; then any-level `rendered`; then stderr's last 20 lines. Errors come first because `observation._describe` keeps only the first 20 lines — interleaved, warnings would push the actual compiler error out of frame. Never rebuild a detail from structured fields; that reimplements rustc's formatting and drifts by version.

**Configuration mismatch versus real failure (step 4):**

```
errors = messages with level == "error" AND a non-empty spans list

no errors                                          ->  execution-failed
every error carries a child note containing
  "found an item that was configured out"          ->  drop this workspace
any error without it                               ->  execution-failed
```

- **`spans`, not `code`, is the discriminator.** Rust 1.79 emits `aborting due to N previous errors` as an extra `code: None` error on *every* failure; counting it makes "all configured out" permanently false there, silently disabling the rule on the support floor. And `compile_error!` has `code: None` with a primary span — a deliberate hard failure that a `code`-based rule would wrongly drop.
- **The note text is observed, not contracted** (identical across 1.79/1.85/1.96; the error prose is not). 1.85 adds `the item is gated here`, so test for **one substring's presence**, never for set equality. If rustc changes the wording, recognition is lost and behaviour reverts to `Failed` — the safe direction.
- **The rule is not exhaustive and the spec says so.** A bare-path reference to a `cfg`-hidden item gets no note on 1.79/1.85. Those workspaces become `Failed`. Completeness is lost, soundness is not.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_clippy_parser.py`. Use these helpers at the top:

```python
"""One `cargo clippy` invocation's stdout into one AnalysisMeasurement."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import pytest

from ebpy.tools.clippy._errors import ClippyFailedError, ClippyInvalidOutputError
from ebpy.tools.clippy._parser import parse_clippy_output
from ebpy.tools.clippy._topology import RustWorkspace

if TYPE_CHECKING:
    from ebpy.models import AnalysisMeasurement

WORKSPACE = RustWorkspace(root=PurePosixPath("."), target_directory=Path("/t"), packages=(".",))


def _line(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


def _warning(file: str, code: str = "clippy::needless_return", line: int = 1) -> str:
    return _line(
        {
            "reason": "compiler-message",
            "message": {
                "level": "warning",
                "message": "needless return",
                "rendered": "warning: needless return",
                "code": {"code": code},
                "spans": [
                    {"is_primary": True, "file_name": file, "line_start": line, "column_start": 1}
                ],
            },
        }
    )


def _error(*, spans: bool = True, configured_out: bool = False, rendered: str = "error: boom") -> str:
    children = (
        [{"message": "found an item that was configured out"}] if configured_out else [{"message": "note"}]
    )
    return _line(
        {
            "reason": "compiler-message",
            "message": {
                "level": "error",
                "message": "boom",
                "rendered": rendered,
                "code": None,
                "spans": [{"is_primary": True, "file_name": "src/lib.rs", "line_start": 1, "column_start": 1}]
                if spans
                else [],
                "children": children,
            },
        }
    )


_FINISHED_OK = _line({"reason": "build-finished", "success": True})
_FINISHED_BAD = _line({"reason": "build-finished", "success": False})


def _parse(stdout: str, tmp_path: Path, *, stderr: str = "", code: int = 0) -> AnalysisMeasurement:
    return parse_clippy_output(stdout, stderr, code, workspace=WORKSPACE, repo_root=tmp_path)
```

Then the cases:

```python
def test_a_warning_with_a_primary_span_becomes_a_cell(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    result = _parse("\n".join([_warning("src/lib.rs"), _FINISHED_OK]), tmp_path)
    assert result.cells == {"src/lib.rs": {"clippy:clippy::needless_return": 1}}


def test_the_clippy_prefix_is_kept_in_the_rule_id(tmp_path: Path) -> None:
    """rustc's own lints share this stream; stripping `clippy::` merges two namespaces."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    result = _parse("\n".join([_warning("src/lib.rs", code="unused_variables"), _FINISHED_OK]), tmp_path)
    assert "clippy:unused_variables" in result.cells["src/lib.rs"]


def test_a_line_that_does_not_start_with_a_brace_is_ignored(tmp_path: Path) -> None:
    """A procedural macro writing to stdout lands in this stream; cargo documents the `{` test."""
    stdout = "\n".join(["hello from a macro", _FINISHED_OK])
    assert _parse(stdout, tmp_path).cells == {}


def test_a_brace_line_that_is_not_json_is_invalid_output(tmp_path: Path) -> None:
    with pytest.raises(ClippyInvalidOutputError):
        _parse("\n".join(["{not json", _FINISHED_OK]), tmp_path)


def test_output_with_no_json_object_at_all_is_execution_failed(tmp_path: Path) -> None:
    """cargo dying silently is the tool failing, not ebpy failing to read it."""
    with pytest.raises(ClippyFailedError) as caught:
        _parse("plain text\n", tmp_path, code=101)
    assert not isinstance(caught.value, ClippyInvalidOutputError)


def test_a_missing_build_finished_is_invalid_output(tmp_path: Path) -> None:
    with pytest.raises(ClippyInvalidOutputError):
        _parse(_warning("src/lib.rs"), tmp_path)


def test_two_build_finished_messages_are_invalid_output(tmp_path: Path) -> None:
    with pytest.raises(ClippyInvalidOutputError):
        _parse("\n".join([_FINISHED_OK, _FINISHED_OK]), tmp_path)


def test_a_non_boolean_success_is_invalid_output(tmp_path: Path) -> None:
    stdout = _line({"reason": "build-finished", "success": 1})
    with pytest.raises(ClippyInvalidOutputError):
        _parse(stdout, tmp_path)


def test_a_broken_line_beside_a_successful_finish_is_still_invalid_output(tmp_path: Path) -> None:
    """Nothing can be concluded from output that cannot be read, success marker included."""
    with pytest.raises(ClippyInvalidOutputError):
        _parse("\n".join([_line({"reason": 7}), _FINISHED_OK]), tmp_path)


def test_a_nonzero_exit_with_a_successful_finish_is_execution_failed(tmp_path: Path) -> None:
    """Neither contract implies the other, so both are required."""
    with pytest.raises(ClippyFailedError):
        _parse(_FINISHED_OK, tmp_path, code=1)


def test_a_failed_build_quotes_the_error_level_rendered_text(tmp_path: Path) -> None:
    """Discarding non-warnings early loses exactly the lines a reader needs."""
    stdout = "\n".join([_warning("src/lib.rs"), _error(rendered="error[E0308]: mismatched"), _FINISHED_BAD])
    with pytest.raises(ClippyFailedError) as caught:
        _parse(stdout, tmp_path, code=101)
    assert "E0308" in caught.value.detail
    assert caught.value.detail.index("E0308") < len(caught.value.detail)


def test_a_failed_build_with_no_rendered_text_falls_back_to_stderr(tmp_path: Path) -> None:
    with pytest.raises(ClippyFailedError) as caught:
        _parse(_FINISHED_BAD, tmp_path, stderr="linker not found", code=101)
    assert "linker not found" in caught.value.detail


def test_a_failure_whose_errors_are_all_configured_out_drops_the_workspace(tmp_path: Path) -> None:
    """ebpy measures one build configuration; code outside it is not a broken repository."""
    stdout = "\n".join([_error(configured_out=True), _FINISHED_BAD])
    result = _parse(stdout, tmp_path, code=101)
    assert result.cells == {}
    assert [s.root for s in result.unmeasured] == ["."]
    assert result.unmeasured[0].packages == (".",)


def test_one_error_without_the_note_makes_the_whole_build_a_real_failure(tmp_path: Path) -> None:
    stdout = "\n".join([_error(configured_out=True), _error(configured_out=False), _FINISHED_BAD])
    with pytest.raises(ClippyFailedError):
        _parse(stdout, tmp_path, code=101)


def test_a_spanless_error_is_not_counted_toward_the_configured_out_rule(tmp_path: Path) -> None:
    """Rust 1.79 emits `aborting due to N previous errors` on every failure, with no spans."""
    stdout = "\n".join(
        [_error(configured_out=True), _error(spans=False, configured_out=False), _FINISHED_BAD]
    )
    result = _parse(stdout, tmp_path, code=101)
    assert len(result.unmeasured) == 1


def test_a_compile_error_macro_is_a_real_failure_not_a_configuration_mismatch(tmp_path: Path) -> None:
    """It has code: None and a primary span; a `code`-based rule would wrongly drop it."""
    stdout = "\n".join([_error(configured_out=True), _error(configured_out=False), _FINISHED_BAD])
    with pytest.raises(ClippyFailedError):
        _parse(stdout, tmp_path, code=101)


def test_broken_error_facts_do_not_downgrade_a_failure_to_invalid_output(tmp_path: Path) -> None:
    """These are read only once failure is certain; strictness there is a downgrade, not a check."""
    stdout = "\n".join(
        [
            _line(
                {
                    "reason": "compiler-message",
                    "message": {
                        "level": "error",
                        "message": "boom",
                        "code": None,
                        "spans": "not a list",
                        "children": 7,
                    },
                }
            ),
            _FINISHED_BAD,
        ]
    )
    with pytest.raises(ClippyFailedError) as caught:
        _parse(stdout, tmp_path, code=101)
    assert not isinstance(caught.value, ClippyInvalidOutputError)


def test_an_unknown_level_is_never_type_checked_further(tmp_path: Path) -> None:
    """rustc documents that enumerated fields may gain values; strictness there is a time bomb."""
    stdout = "\n".join(
        [
            _line(
                {
                    "reason": "compiler-message",
                    "message": {"level": "failure-note", "message": "x", "code": 7, "spans": 9},
                }
            ),
            _FINISHED_OK,
        ]
    )
    assert _parse(stdout, tmp_path).cells == {}


def test_an_unknown_reason_is_ignored_rather_than_rejected(tmp_path: Path) -> None:
    stdout = "\n".join([_line({"reason": "future-cargo-message", "payload": 1}), _FINISHED_OK])
    assert _parse(stdout, tmp_path).cells == {}


def test_a_broken_code_object_without_a_primary_span_is_only_discarded(tmp_path: Path) -> None:
    """Checking a value that is never read makes a run fail for nothing."""
    stdout = "\n".join(
        [
            _line(
                {
                    "reason": "compiler-message",
                    "message": {"level": "warning", "message": "x", "code": {"code": 7}, "spans": []},
                }
            ),
            _FINISHED_OK,
        ]
    )
    assert _parse(stdout, tmp_path).cells == {}


def test_a_rule_code_containing_a_newline_is_invalid_output(tmp_path: Path) -> None:
    """qualify_rule raises ValueError on those, and a bare ValueError breaks the parser's contract."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    stdout = "\n".join([_warning("src/lib.rs", code="a\nb"), _FINISHED_OK])
    with pytest.raises(ClippyInvalidOutputError):
        _parse(stdout, tmp_path)


def test_the_lowest_primary_span_is_chosen_deterministically(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    for name in ("a.rs", "b.rs"):
        (tmp_path / "src" / name).write_text("pub fn f() {}\n", encoding="utf-8")
    stdout = "\n".join(
        [
            _line(
                {
                    "reason": "compiler-message",
                    "message": {
                        "level": "warning",
                        "message": "x",
                        "code": {"code": "clippy::x"},
                        "spans": [
                            {"is_primary": True, "file_name": "src/b.rs", "line_start": 2, "column_start": 1},
                            {"is_primary": True, "file_name": "src/a.rs", "line_start": 9, "column_start": 1},
                        ],
                    },
                }
            ),
            _FINISHED_OK,
        ]
    )
    assert set(_parse(stdout, tmp_path).cells) == {"src/a.rs"}


def test_a_path_that_cannot_be_placed_becomes_unattributed_not_invalid_output(tmp_path: Path) -> None:
    stdout = "\n".join([_warning("/etc/passwd.rs"), _FINISHED_OK])
    result = _parse(stdout, tmp_path)
    assert result.cells == {}
    assert [f.file for f in result.unattributed] == ["/etc/passwd.rs"]


def test_generated_code_is_dropped_even_when_its_out_dir_arrives_later(tmp_path: Path) -> None:
    """build-script-executed can follow the messages it explains; one pass loses them."""
    out = "/build/x-abc/out"
    stdout = "\n".join(
        [
            _warning(f"{out}/gen.rs"),
            _line({"reason": "build-script-executed", "out_dir": out}),
            _FINISHED_OK,
        ]
    )
    result = _parse(stdout, tmp_path)
    assert result.cells == {}
    assert result.unattributed == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_clippy_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ebpy.tools.clippy._parser'`

- [ ] **Step 3: Write the scanner half**

Create `src/ebpy/tools/clippy/_parser.py`, starting with the value types and the line scan:

```python
"""One `cargo clippy` invocation's stdout into one AnalysisMeasurement.

One invocation, one call. "Exactly one build-finished" is an invariant of a single cargo
run, so concatenating two workspaces' output before parsing would break it — which is why
this function takes the workspace it is parsing rather than a list of them.

Two passes over the messages, not one: `build-script-executed` may arrive after the
diagnostics it explains, so every `out_dir` is collected before any path is classified.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ebpy.cell_key import qualify_rule
from ebpy.models import AnalysisMeasurement, CellCounts, UnattributedFinding, UnmeasuredScope

from ._errors import ClippyFailedError, ClippyInvalidOutputError
from ._paths import attribute_path, normalize_out_dir

if TYPE_CHECKING:
    from pathlib import Path

    from ._topology import RustWorkspace

# Observed identical on 1.79, 1.85 and 1.96 — the error prose around it is not. Tested for
# by presence of this one substring, never by matching the note set: 1.85 adds a second note
# ("the item is gated here"), and an equality test would have broken there. If rustc ever
# rewords it, recognition is lost and the behaviour reverts to Failed, which is the safe
# direction: a workspace stops being dropped rather than being dropped wrongly.
_CONFIGURED_OUT = "found an item that was configured out"

_STDERR_TAIL = 20


@dataclass(frozen=True)
class _Candidate:
    """One warning that survived every staged check, before its path was classified."""

    file: str
    line: int
    column: int
    code: str
    message: str


@dataclass
class _Scan:
    """Everything one pass over stdout collected, before any verdict is reached."""

    objects: int = 0
    finished: list[bool] = field(default_factory=list)
    out_dirs: list[str] = field(default_factory=list)
    candidates: list[_Candidate] = field(default_factory=list)
    error_rendered: list[str] = field(default_factory=list)
    any_rendered: list[str] = field(default_factory=list)
    # Errors carrying at least one span, and whether each was explained by a cfg note. Read
    # leniently, and only once failure is certain.
    spanned_errors: list[bool] = field(default_factory=list)


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ClippyInvalidOutputError(detail)


def _positive_int(value: object) -> bool:
    # `isinstance(True, int)` is true, so a bare isinstance check would read `true` as line 1.
    return type(value) is int and value > 0


def _configured_out(message: dict[str, Any]) -> bool:
    """Whether rustc explained this error as a reference to a `cfg`-excluded item.

    Read but never type-checked. This is consulted only after the build is known to have
    failed, so rejecting a malformed value here would downgrade a real `execution-failed`
    into `invalid-output`. An unreadable value falls to False, which means "real failure",
    which means the workspace stays measured — the safe direction, automatically.
    """
    children = message.get("children")
    if not isinstance(children, list):
        return False
    return any(
        isinstance(child, dict) and isinstance(text := child.get("message"), str) and _CONFIGURED_OUT in text
        for child in children
    )


def _read_warning(message: dict[str, Any]) -> _Candidate | None:
    """Apply the staged checks a warning must pass to become a cell, or return None to discard."""
    code = message.get("code")
    _require(code is None or isinstance(code, dict), "clippy reported a message code of an unexpected shape")
    if code is None:
        return None
    spans = message.get("spans")
    _require(isinstance(spans, list), "clippy reported spans that are not a list")
    primaries = []
    for span in spans:
        _require(isinstance(span, dict), "clippy reported a span of an unexpected shape")
        primary = span.get("is_primary", False)
        _require(isinstance(primary, bool), "clippy reported a non-boolean is_primary")
        if primary:
            primaries.append(span)
    if not primaries:
        return None
    for span in primaries:
        _require(
            isinstance(span.get("file_name"), str) and bool(span["file_name"]),
            "clippy reported a primary span without a file name",
        )
        _require(
            _positive_int(span.get("line_start")) and _positive_int(span.get("column_start")),
            "clippy reported a primary span without a positive line and column",
        )
    # Checked last, because a message with no primary span is discarded regardless: making a
    # run fail over a value it never reads is the one thing the staged order exists to avoid.
    local = code.get("code")
    _require(
        isinstance(local, str) and bool(local) and "\n" not in local and "\r" not in local,
        "clippy reported a rule code that cannot be part of a cell key",
    )
    chosen = min(primaries, key=lambda s: (s["file_name"], s["line_start"], s["column_start"]))
    text = message.get("message")
    _require(isinstance(text, str), "clippy reported a message text that is not a string")
    return _Candidate(
        file=chosen["file_name"],
        line=chosen["line_start"],
        column=chosen["column_start"],
        code=local,
        message=text,
    )
```

- [ ] **Step 4: Write the scan loop and the verdict**

Append to the same file:

```python
def _scan(stdout: str) -> _Scan:
    """Read every interpretable line once, checking only the fields ebpy actually reads."""
    scan = _Scan()
    for line in stdout.splitlines():
        # Cargo's own documented workaround for procedural-macro output on this stream is
        # exactly this test. `lstrip()` would only blur the boundary it draws.
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ClippyInvalidOutputError(f"clippy produced an unreadable JSON line: {error}") from error
        _require(isinstance(payload, dict), "clippy produced a JSON value that is not an object")
        reason = payload.get("reason")
        _require(isinstance(reason, str), "clippy produced a message without a string reason")
        scan.objects += 1

        if reason == "build-finished":
            success = payload.get("success")
            _require(isinstance(success, bool), "clippy reported a non-boolean build-finished success")
            scan.finished.append(success)
            continue
        if reason == "build-script-executed":
            out_dir = payload.get("out_dir")
            _require(isinstance(out_dir, str), "cargo reported a build script without a string out_dir")
            scan.out_dirs.append(normalize_out_dir(out_dir))
            continue
        # Unknown and unreadable are different: a reason ebpy does not recognise is ignored,
        # exactly as rustc's forward-compatibility contract asks.
        if reason != "compiler-message":
            continue

        message = payload.get("message")
        _require(isinstance(message, dict), "clippy reported a compiler message of an unexpected shape")
        level = message.get("level")
        _require(isinstance(level, str), "clippy reported a message without a string level")
        # Collected before the level is dispatched on, because a failed build's detail needs
        # the error-level text and discarding non-warnings first throws it away.
        if isinstance(rendered := message.get("rendered"), str):
            scan.any_rendered.append(rendered)
            if level == "error":
                scan.error_rendered.append(rendered)
        if level == "error":
            spans = message.get("spans")
            if isinstance(spans, list) and spans:
                scan.spanned_errors.append(_configured_out(message))
            continue
        if level != "warning":
            continue
        if (candidate := _read_warning(message)) is not None:
            scan.candidates.append(candidate)
    return scan


def _failure_detail(scan: _Scan, stderr: str) -> str:
    """Quote what the compiler said, errors first.

    `observation._describe` keeps only the leading lines, so interleaving warnings would push
    the actual compiler error out of frame. Never rebuilt from structured fields: that would
    reimplement rustc's formatting and drift with every version.
    """
    if scan.error_rendered:
        return "\n".join(scan.error_rendered)
    if scan.any_rendered:
        return "\n".join(scan.any_rendered)
    return "\n".join(stderr.splitlines()[-_STDERR_TAIL:])


def _measure(scan: _Scan, workspace: RustWorkspace, repo_root: Path) -> AnalysisMeasurement:
    cells: CellCounts = {}
    unattributed: list[UnattributedFinding] = []
    root = workspace.root.as_posix()
    for candidate in scan.candidates:
        verdict = attribute_path(
            candidate.file, workspace_root=root, repo_root=repo_root, out_dirs=scan.out_dirs
        )
        if verdict.kind == "generated":
            continue
        if verdict.kind == "unattributed":
            # The reported path verbatim, not the prefixed one: a reader has to be able to
            # match this against clippy's own output, and a path ebpy assembled would send
            # them looking for a file that was never named.
            unattributed.append(
                UnattributedFinding(file=candidate.file, line=candidate.line, message=candidate.message)
            )
            continue
        try:
            rule = qualify_rule("clippy", candidate.code)
        except ValueError as error:
            raise ClippyInvalidOutputError(f"clippy reported an unusable rule code: {error}") from error
        file_cells = cells.setdefault(verdict.path, {})
        file_cells[rule] = file_cells.get(rule, 0) + 1
    return AnalysisMeasurement(cells=cells, unattributed=tuple(unattributed))


def parse_clippy_output(
    stdout: str, stderr: str, returncode: int, *, workspace: RustWorkspace, repo_root: Path
) -> AnalysisMeasurement:
    """Turn one invocation's output into a measurement, or say why it is not one.

    The order of the checks below is itself the specification. Unreadable output comes first
    because nothing can be concluded from it — not even from a `success: true` sitting beside
    a broken line. "No output at all" comes before "no completion marker" because cargo dying
    silently is the tool failing, while cargo speaking without finishing is ebpy failing to
    read it, and those deserve different words.

    A build that failed only because it references items this configuration excludes returns
    the workspace as unmeasured rather than raising: it is a range ebpy does not cover, not a
    broken repository.
    """
    scan = _scan(stdout)
    if scan.objects == 0:
        headline = f"cargo clippy produced no output (exit {returncode})"
        tail = "\n".join(stderr.splitlines()[-_STDERR_TAIL:])
        raise ClippyFailedError(headline, detail=f"{headline}:\n{tail}" if tail else headline)
    _require(len(scan.finished) == 1, "clippy did not report exactly one build-finished message")

    # Both are required: the contract guarantees `success` describes the build, and separately
    # that a normal cargo command reports success with exit 0. Neither implies the other.
    if not scan.finished[0] or returncode != 0:
        if scan.spanned_errors and all(scan.spanned_errors):
            return AnalysisMeasurement(
                cells={},
                unmeasured=(
                    UnmeasuredScope(root=workspace.root.as_posix(), packages=workspace.packages),
                ),
            )
        raise ClippyFailedError(
            f"cargo clippy could not build this workspace (exit {returncode})",
            detail=_failure_detail(scan, stderr),
        )
    return _measure(scan, workspace, repo_root)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_clippy_parser.py -v`
Expected: PASS

- [ ] **Step 6: Format and commit**

```bash
git add src/ebpy/tools/clippy/_parser.py tests/test_clippy_parser.py && git commit -m "feat(clippy): parse one cargo clippy invocation into a measurement"
```

---

## Task 10: Probe, invoke, aggregate — and the `ClippyAnalyzer`

**Files:**
- Create: `src/ebpy/tools/clippy/_runner.py`, `src/ebpy/tools/clippy/analyzer.py`
- Modify: `src/ebpy/tools/clippy/__init__.py` (re-export `run_clippy_check`, `ClippyAnalyzer`)
- Test: `tests/test_clippy_runner.py`

**Interfaces:**
- Consumes: `rust_topology`, `RustWorkspace` (Task 7); `parse_clippy_output` (Task 9); `ebpy.util.run`; `Language` (Task 1).
- Produces: `run_clippy_check(cwd: Path) -> AnalysisMeasurement`; `ClippyAnalyzer` with `name="clippy"`, `noun="Rust lint warnings"`, `language="rust"`.

**The exact commands, and why each flag is load-bearing:**

```
probe    (cwd = workspace_root):  cargo clippy --version
measure  (cwd = workspace_root):  cargo clippy --workspace --message-format=json \
                                      --target-dir <target_directory>/ebpy-clippy \
                                      -- --cap-lints warn
```

- **Probe per workspace, not per repository.** rustup picks the toolchain nearest the cwd, so a nested `rust-toolchain.toml` means a repository-root probe measured a different toolchain than the one that will run.
- **`OSError` becomes `ClippyNotFoundError` inside the probe.** `util.run` calls `subprocess.run` directly, so a missing executable raises. mypy's analyzer catches `OSError` as `Failed` — but only because `find_mypy` already proved the executable exists, making an `OSError` there a genuine anomaly. Copying that except-clause here turns "cargo is not installed" into `Failed`, when `docs/measurement-seam.md` says executable-not-found is `Unavailable`.
- **The probe reads stdout's opening.** `cargo clippy` is an *external subcommand*, and a cargo alias can shadow it — cargo warns and proceeds, exit 0. `stdout.startswith("clippy ")` catches the accident. This is a *measured* contract, not a documented one, which is why the integration test runs at both ends of the support range. It does not defeat an alias that impersonates the string; it is not meant to. Never parse the warning text — it is documented as becoming a hard error later. Never use `shutil.which("cargo-clippy")` — rustup's shim resolves toolchains independently of PATH.
- **`--workspace` is not optional.** In a non-virtual workspace with no package selection, cargo builds only the root package or `default-members`; members vanish silently and enter the ceiling as zero, and `prune` then lowers it wrongly.
- **`-- --cap-lints warn` is not optional.** `[lints.clippy] all = "deny"`, `#![deny(...)]` and `RUSTFLAGS=-Dwarnings` all promote lints to errors and set `success: false`, so a repository using the pattern Clippy's own CI guide recommends could never freeze. Hard errors are unaffected — `--cap-lints` caps lint *levels* only, and E0308 stays an error.
- **A private `--target-dir`.** The extra rustc argument enters the fingerprint, so ebpy's runs and the developer's own `cargo clippy` invalidate each other's cache. Placing it *under* cargo's reported `target_directory` keeps `cargo clean` and the existing `.gitignore` working.
- **No `--all-targets`.** It compiles the lib twice (lib and test harness) and doubles every diagnostic, with both copies indistinguishable (`kind: ["lib"]` both times).

**Aggregation — three stages, no priority between them; whichever settles first ends it:**

| stage | condition | observation |
| --- | --- | --- |
| discovery | cargo absent | `Unavailable` |
| discovery | one candidate's metadata failed | drop it into `unmeasured` |
| discovery | *every* candidate failed | that failure's classification |
| discovery | zero workspaces | `Unavailable` |
| probe | any workspace's probe fails | `Unavailable` |
| measure | any workspace really fails | `Failed` |
| measure | the rest succeed | summed into one `Measured` |

- **Probe every workspace before measuring any.** Otherwise a full compile finishes and *then* the second workspace's probe fails.
- **Stop at the first failure in each stage.** Once the whole observation is settled, the remaining work changes nothing and costs a full build.
- **Ordering is by `workspace_root` ascending**, never by the order metadata was invoked — candidate order comes from `git ls-files`, and a detail message should not change when git's output order does.
- **`merge_cells` cannot be used here.** It raises `ValueError` on a repeated `file × rule`, and its docstring says why: correct namespacing makes that impossible *across analyzers*. Across workspaces of the *same* analyzer it is legitimate — cargo targets can set `path` relative to their manifest, so two workspaces may compile one `.rs`. **Add the counts.** Measuring the same repository twice still yields the same number, so the ceiling reproduces. Concatenate `unattributed` in workspace order, no de-duplication: two workspaces compiling one file failed to place it twice.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_clippy_runner.py`:

```python
"""Probing, invoking and aggregating clippy across a repository's workspaces."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import pytest

from ebpy.measurement import Failed, Measured, Unavailable
from ebpy.models import AnalysisMeasurement
from ebpy.tools.clippy import _runner
from ebpy.tools.clippy._errors import ClippyFailedError, ClippyNoWorkspaceError, ClippyNotFoundError
from ebpy.tools.clippy._runner import run_clippy_check
from ebpy.tools.clippy._topology import RustTopology, RustWorkspace
from ebpy.tools.clippy.analyzer import ClippyAnalyzer
from ebpy.util import ExecResult

if TYPE_CHECKING:
    from collections.abc import Callable

_VERSION_OK = ExecResult(code=0, stdout="clippy 0.1.96 (abc 2026-05-25)\n", stderr="")
_FINISHED_OK = json.dumps({"reason": "build-finished", "success": True})


def _workspace(root: str) -> RustWorkspace:
    return RustWorkspace(root=PurePosixPath(root), target_directory=Path("/t"), packages=(root,))


def _install(
    monkeypatch: pytest.MonkeyPatch,
    topology: RustTopology,
    responder: Callable[[list[str], Path], ExecResult],
) -> None:
    monkeypatch.setattr(_runner, "rust_topology", lambda _cwd: topology)
    monkeypatch.setattr(_runner, "run", responder)


def test_a_repository_with_no_workspace_has_nothing_for_clippy_to_run_against(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, RustTopology((), ()), lambda _a, _c: _VERSION_OK)
    with pytest.raises(ClippyNoWorkspaceError):
        run_clippy_check(tmp_path)


def test_an_aliased_cargo_clippy_that_does_not_name_itself_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cargo alias shadows the external subcommand and still exits 0; the name is the tell."""
    _install(
        monkeypatch,
        RustTopology((_workspace("."),), ()),
        lambda _a, _c: ExecResult(code=0, stdout="", stderr="warning: user-defined alias"),
    )
    with pytest.raises(ClippyNotFoundError):
        run_clippy_check(tmp_path)


def test_a_missing_cargo_during_the_probe_is_unavailable_not_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`docs/measurement-seam.md` puts executable-not-found on the Unavailable side."""

    def _boom(_argv: list[str], _cwd: Path) -> ExecResult:
        raise FileNotFoundError("cargo")

    _install(monkeypatch, RustTopology((_workspace("."),), ()), _boom)
    with pytest.raises(ClippyNotFoundError):
        run_clippy_check(tmp_path)


def test_every_workspace_is_probed_before_any_is_compiled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise a full build finishes before the second probe reports the component missing."""
    calls: list[str] = []

    def _respond(argv: list[str], _cwd: Path) -> ExecResult:
        calls.append(argv[2])
        if argv[2] == "--version":
            return _VERSION_OK if len(calls) == 1 else ExecResult(code=1, stdout="", stderr="no clippy")
        return ExecResult(code=0, stdout=_FINISHED_OK, stderr="")

    _install(monkeypatch, RustTopology((_workspace("a"), _workspace("b")), ()), _respond)
    with pytest.raises(ClippyNotFoundError):
        run_clippy_check(tmp_path)
    assert "--workspace" not in calls


def test_the_measurement_command_carries_every_required_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []

    def _respond(argv: list[str], _cwd: Path) -> ExecResult:
        seen.append(argv)
        if "--version" in argv:
            return _VERSION_OK
        return ExecResult(code=0, stdout=_FINISHED_OK, stderr="")

    _install(monkeypatch, RustTopology((_workspace("."),), ()), _respond)
    run_clippy_check(tmp_path)
    measure = seen[-1]
    assert "--workspace" in measure
    assert "--message-format=json" in measure
    assert measure[measure.index("--target-dir") + 1].endswith("ebpy-clippy")
    assert measure[-3:] == ["--", "--cap-lints", "warn"]


def test_one_workspace_failing_makes_the_whole_measurement_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial success as Measured would put the failed workspace's cells in as zero."""

    def _respond(argv: list[str], cwd: Path) -> ExecResult:
        if "--version" in argv:
            return _VERSION_OK
        if cwd.name == "b":
            return ExecResult(code=101, stdout="", stderr="broken")
        return ExecResult(code=0, stdout=_FINISHED_OK, stderr="")

    _install(monkeypatch, RustTopology((_workspace("a"), _workspace("b")), ()), _respond)
    with pytest.raises(ClippyFailedError) as caught:
        run_clippy_check(tmp_path)
    assert "b" in caught.value.detail


def test_cells_from_two_workspaces_are_added_rather_than_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`merge_cells` raises on a repeated file x rule; two workspaces may compile one .rs."""
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")
    warning = json.dumps(
        {
            "reason": "compiler-message",
            "message": {
                "level": "warning",
                "message": "x",
                "code": {"code": "clippy::x"},
                "spans": [
                    {
                        "is_primary": True,
                        "file_name": "shared/lib.rs",
                        "line_start": 1,
                        "column_start": 1,
                    }
                ],
            },
        }
    )

    def _respond(argv: list[str], _cwd: Path) -> ExecResult:
        if "--version" in argv:
            return _VERSION_OK
        return ExecResult(code=0, stdout="\n".join([warning, _FINISHED_OK]), stderr="")

    _install(monkeypatch, RustTopology((_workspace("."), _workspace("side")), ()), _respond)
    result = run_clippy_check(tmp_path)
    assert result.cells["shared/lib.rs"]["clippy:clippy::x"] == 2


def test_the_topology_unmeasured_scopes_reach_the_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ebpy.models import UnmeasuredScope

    dropped = UnmeasuredScope(root="vendor/dep", packages=("vendor/dep",))

    def _respond(argv: list[str], _cwd: Path) -> ExecResult:
        return _VERSION_OK if "--version" in argv else ExecResult(code=0, stdout=_FINISHED_OK, stderr="")

    _install(monkeypatch, RustTopology((_workspace("."),), (dropped,)), _respond)
    assert run_clippy_check(tmp_path).unmeasured == (dropped,)


def test_the_analyzer_turns_each_error_into_the_right_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single except clause collapsing these three destroys every message a reader can act on."""
    import ebpy.tools.clippy as clippy_package

    cases = {
        ClippyNotFoundError("no cargo"): Unavailable,
        ClippyFailedError("broken"): Failed,
    }
    for error, expected in cases.items():

        def _raise(_cwd: Path, _error: BaseException = error) -> AnalysisMeasurement:
            raise _error

        monkeypatch.setattr(clippy_package, "run_clippy_check", _raise)
        assert isinstance(ClippyAnalyzer().measure(tmp_path), expected)


def test_the_analyzer_names_its_language_and_what_it_finds() -> None:
    """"Clippy lints" would be too narrow: rustc's own lints share this stream and get cells."""
    analyzer = ClippyAnalyzer()
    assert analyzer.name == "clippy"
    assert analyzer.language == "rust"
    assert analyzer.noun == "Rust lint warnings"
```

Add the real-cargo integration block (reuse the `needs_clippy` marker pattern from Task 7 — define it locally in this file too):

```python
def _clippy_available() -> bool:
    if shutil.which("cargo") is None:
        return False
    probe = subprocess.run(["cargo", "clippy", "--version"], capture_output=True, text=True, check=False)
    return probe.returncode == 0 and probe.stdout.startswith("clippy ")


needs_clippy = pytest.mark.skipif(
    not _clippy_available(), reason="needs a toolchain whose `cargo clippy --version` succeeds"
)

_CRATE = "[package]\nname='{name}'\nversion='0.1.0'\nedition='2021'\n"
# `needless_return` is one of clippy's oldest and most stable lints; using a recent one would
# make the expected count depend on the toolchain rather than on the code.
_DIRTY = "pub fn f() -> i32 {\n    return 1;\n}\n"


def _crate(root: Path, name: str, body: str = _DIRTY) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(_CRATE.format(name=name), encoding="utf-8")
    (root / "src" / "lib.rs").write_text(body, encoding="utf-8")


@needs_clippy
def test_a_non_virtual_workspace_measures_every_member(tmp_path: Path) -> None:
    """Without --workspace, cargo builds only the root package and members enter as zero."""
    _crate(tmp_path, "root")
    (tmp_path / "Cargo.toml").write_text(
        _CRATE.format(name="root") + "\n[workspace]\nmembers=['crates/a']\n", encoding="utf-8"
    )
    _crate(tmp_path / "crates" / "a", "a")
    result = run_clippy_check(tmp_path)
    assert set(result.cells) == {"src/lib.rs", "crates/a/src/lib.rs"}


@needs_clippy
def test_a_repository_that_denies_all_clippy_lints_can_still_be_measured(tmp_path: Path) -> None:
    """`--cap-lints warn` is what lets Clippy's own recommended CI setup be frozen at all."""
    _crate(tmp_path, "a")
    (tmp_path / "Cargo.toml").write_text(
        _CRATE.format(name="a") + "\n[lints.clippy]\nall = 'deny'\n", encoding="utf-8"
    )
    result = run_clippy_check(tmp_path)
    assert result.cells["src/lib.rs"]["clippy:clippy::needless_return"] == 1


@needs_clippy
def test_a_cfg_hidden_module_drops_its_workspace_instead_of_failing_the_run(tmp_path: Path) -> None:
    _crate(
        tmp_path,
        "a",
        body="#[cfg(fuzzing)]\npub mod fuzz;\n\npub fn use_it() { crate::fuzz::f(); }\n",
    )
    result = run_clippy_check(tmp_path)
    assert result.cells == {}
    assert [s.root for s in result.unmeasured] == ["."]


@needs_clippy
def test_a_misspelled_module_is_a_real_failure_and_is_never_dropped(tmp_path: Path) -> None:
    """A typo produces the same E0433 as a cfg-hidden module; only the note tells them apart."""
    _crate(tmp_path, "a", body="pub fn use_it() { crate::nosuch::f(); }\n")
    with pytest.raises(ClippyFailedError):
        run_clippy_check(tmp_path)


@needs_clippy
def test_a_type_error_is_a_real_failure(tmp_path: Path) -> None:
    _crate(tmp_path, "a", body="pub fn f() -> i32 { \"x\" }\n")
    with pytest.raises(ClippyFailedError):
        run_clippy_check(tmp_path)


@needs_clippy
def test_a_compile_error_macro_beside_a_cfg_failure_is_a_real_failure(tmp_path: Path) -> None:
    """`compile_error!` has code: None; a code-based rule would drop it on 1.79 and 1.85."""
    _crate(
        tmp_path,
        "a",
        body=(
            "#[cfg(fuzzing)]\npub mod fuzz;\n"
            "pub fn use_it() { crate::fuzz::f(); }\n"
            "compile_error!(\"select a backend\");\n"
        ),
    )
    with pytest.raises(ClippyFailedError):
        run_clippy_check(tmp_path)


@needs_clippy
def test_a_remapped_path_produces_no_cells_and_leaves_the_run_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The remap rewrites the path textually and still exits 0 with success=true."""
    _crate(tmp_path, "a")
    monkeypatch.setenv("RUSTFLAGS", "--remap-path-prefix=src=shadow")
    result = run_clippy_check(tmp_path)
    assert result.cells == {}
    assert result.unattributed


@needs_clippy
def test_build_script_output_is_dropped_and_the_measurement_still_succeeds(tmp_path: Path) -> None:
    """Treating generated code as unattributed would make freeze refuse this repository forever."""
    _crate(tmp_path, "gendemo", body='include!(concat!(env!("OUT_DIR"), "/gen.rs"));\n')
    (tmp_path / "build.rs").write_text(
        "use std::{env, fs, path::Path};\n"
        "fn main() {\n"
        "    let out = env::var(\"OUT_DIR\").unwrap();\n"
        "    fs::write(Path::new(&out).join(\"gen.rs\"), "
        "\"pub fn g() -> i32 { return 1; }\\n\").unwrap();\n"
        "}\n",
        encoding="utf-8",
    )
    result = run_clippy_check(tmp_path)
    assert result.unattributed == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_clippy_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ebpy.tools.clippy._runner'`

- [ ] **Step 3: Write the runner**

Create `src/ebpy/tools/clippy/_runner.py`:

```python
"""Running clippy across every Cargo workspace this repository holds.

Probe, then measure, then aggregate — with the probe finished for every workspace before the
first compile starts, so a missing clippy component is reported before an hour of building
rather than after it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ebpy.models import AnalysisMeasurement, CellCounts, UnattributedFinding, UnmeasuredScope
from ebpy.util import run

from ._errors import ClippyFailedError, ClippyNotFoundError, ClippyNoWorkspaceError
from ._parser import parse_clippy_output
from ._topology import RustWorkspace, rust_topology

if TYPE_CHECKING:
    from pathlib import Path

# Kept apart from the developer's own cache. The extra rustc argument below enters cargo's
# fingerprint, so sharing one target directory makes ebpy's runs and a hand-run
# `cargo clippy` invalidate each other, turning every alternation into a full rebuild. It sits
# *under* the directory cargo reported so `cargo clean` and the existing .gitignore still cover it.
_TARGET_SUBDIR = "ebpy-clippy"

_INSTALL_HINT = (
    "cargo or the clippy component could not be run here. On a rustup-managed toolchain, "
    "`rustup component add clippy` installs it."
)


def _workspace_dir(repo_root: Path, workspace: RustWorkspace) -> Path:
    root = workspace.root.as_posix()
    return repo_root if root == "." else repo_root / root


def _probe(directory: Path) -> None:
    """Confirm a real `cargo clippy` answers in this workspace's directory.

    Per workspace, because rustup resolves the toolchain from the current directory: a nested
    `rust-toolchain.toml` means a probe at the repository root measured a different toolchain
    than the one that will actually run.

    The exit code alone is not enough. `cargo clippy` is an external subcommand and a cargo
    alias can shadow it — cargo warns and carries on with exit 0. A real clippy names itself,
    so the opening of stdout is what is checked. That is a measured behaviour rather than a
    documented one, which is why the integration tests run at both ends of the support range.
    The warning's wording is deliberately not read: it is documented as becoming a hard error,
    at which point the non-zero exit catches it anyway.
    """
    try:
        result = run(["cargo", "clippy", "--version"], directory)
    except OSError as error:
        # Converted here rather than caught in the analyzer: `util.run` calls subprocess
        # directly, so a missing executable raises, and mypy's `except OSError -> Failed` is
        # only correct there because `find_mypy` proved the executable exists first.
        raise ClippyNotFoundError(_INSTALL_HINT, detail=f"{_INSTALL_HINT}\n{error}") from error
    if result.code != 0 or not result.stdout.startswith("clippy "):
        detail = "\n".join([_INSTALL_HINT, result.stderr.strip()]).strip()
        raise ClippyNotFoundError(_INSTALL_HINT, detail=detail)


def _measure_workspace(
    directory: Path, workspace: RustWorkspace, repo_root: Path
) -> AnalysisMeasurement:
    argv = [
        "cargo",
        "clippy",
        "--workspace",
        "--message-format=json",
        "--target-dir",
        str(workspace.target_directory / _TARGET_SUBDIR),
        "--",
        "--cap-lints",
        "warn",
    ]
    result = run(argv, directory)
    return parse_clippy_output(
        result.stdout, result.stderr, result.code, workspace=workspace, repo_root=repo_root
    )


def run_clippy_check(cwd: Path) -> AnalysisMeasurement:
    """Measure every Cargo workspace in this repository as one value.

    One workspace failing fails the whole measurement: reporting partial success as Measured
    would enter the failed workspace's cells as zero, and `prune` would then lower a ceiling
    nobody re-measured.
    """
    repo_root = cwd.resolve()
    topology = rust_topology(cwd)
    if not topology.workspaces:
        raise ClippyNoWorkspaceError(
            "no Cargo workspace in this repository",
            detail="cargo resolved no workspace here, so clippy has nothing to measure.",
        )

    # Ascending by repository-relative root, never by the order metadata happened to run:
    # candidate order comes from `git ls-files`, and a message should not change wording
    # because git's output order changed.
    ordered = sorted(topology.workspaces, key=lambda workspace: workspace.root.as_posix())
    for workspace in ordered:
        _probe(_workspace_dir(repo_root, workspace))

    cells: CellCounts = {}
    unattributed: list[UnattributedFinding] = []
    unmeasured: list[UnmeasuredScope] = list(topology.unmeasured)
    for workspace in ordered:
        root = workspace.root.as_posix()
        try:
            part = _measure_workspace(_workspace_dir(repo_root, workspace), workspace, repo_root)
        except ClippyFailedError as error:
            raise type(error)(
                f"{root}: {error.summary}", detail=f"{root}:\n{error.detail}"
            ) from error
        for file, rules in part.cells.items():
            target = cells.setdefault(file, {})
            for rule, count in rules.items():
                # Added, not rejected: `merge_cells` forbids a repeated file x rule because
                # namespacing makes it impossible *across analyzers*, but two workspaces of
                # one analyzer may legitimately compile the same .rs via a relative `path`.
                # A count is what this measurement observed, and it reproduces.
                target[rule] = target.get(rule, 0) + count
        unattributed.extend(part.unattributed)
        unmeasured.extend(part.unmeasured)

    return AnalysisMeasurement(
        cells=cells, unattributed=tuple(unattributed), unmeasured=tuple(unmeasured)
    )
```

- [ ] **Step 4: Write the analyzer**

Create `src/ebpy/tools/clippy/analyzer.py`:

```python
"""clippy analyzer: runs cargo clippy and classifies the outcome as an observation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import ebpy.tools.clippy
from ebpy.measurement import Failed, Measured, Observation, Unavailable
from ebpy.models import Language

from ._errors import ClippyFailedError, ClippyInvalidOutputError, ClippyUnavailableError

if TYPE_CHECKING:
    from pathlib import Path

    from ebpy.models import AnalysisMeasurement


@dataclass(frozen=True)
class ClippyAnalyzer:
    """clippy analyzer that owns the full observation-building try/except."""

    name: str = "clippy"
    # Not "Clippy lints": rustc's own lints (`unused_variables` and friends) arrive in the
    # same stream and earn cells too, so the noun names what is found, not what found it.
    noun: str = "Rust lint warnings"
    language: Language = "rust"

    def measure(self, cwd: Path) -> Observation[AnalysisMeasurement]:
        """Run clippy against the repository at cwd and return the observation."""
        # Resolved through the package namespace rather than bound here, so a test
        # monkeypatching ebpy.tools.clippy.run_clippy_check reaches the call that runs.
        try:
            return Measured(tool="clippy", value=ebpy.tools.clippy.run_clippy_check(cwd))
        except ClippyUnavailableError as error:
            return Unavailable.from_tool_error("clippy", error)
        except ClippyInvalidOutputError as error:
            return Failed.from_tool_error("clippy", "invalid-output", error)
        except (ClippyFailedError, OSError) as error:
            return Failed.from_tool_error("clippy", "execution-failed", error)
```

- [ ] **Step 5: Re-export from the package**

In `src/ebpy/tools/clippy/__init__.py`, add `from ._runner import run_clippy_check` and `from .analyzer import ClippyAnalyzer`, and add both names to `__all__`. The module docstring gains the seam note: *``run_clippy_check`` is re-exported here as the package's measurement seam: the analyzer resolves it through this namespace so a test can monkeypatch it in one place.*

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_clippy_runner.py -v`
Expected: PASS

- [ ] **Step 7: Format and full suite**

Run: `uv run ruff format . && uv run pytest`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/ebpy/tools/clippy/ tests/test_clippy_runner.py && git commit -m "feat(clippy): probe, measure and aggregate across a repository's workspaces"
```

---

**Stage #2 of the spec (§7) is complete.** The runner exists and is tested; nothing is registered, so no existing repository's behaviour has moved.

---

## Task 11: Register `ClippyAnalyzer`, and stop pointing at a door that does not exist

**Files:**
- Modify: `src/ebpy/tools/registry.py` (`_registry`)
- Modify: `src/ebpy/commands/freeze.py` (`_refusal_reason`, the `"unavailable"` branch)
- Test: `tests/test_tools.py`, `tests/test_freeze.py`

**Interfaces:**
- Consumes: `ClippyAnalyzer` (Task 10).
- Produces: `"clippy"` in `ANALYZERS`, `ANALYZER_NAMES` and therefore in `.ebpy/config.json`'s accepted values (`store/config.py:62` validates against `ANALYZER_NAMES`, so that file needs no change).

**Why this is safe only after Task 4.** Before scoping, registering clippy would put it in every repository's default freeze scope, and `build_global_freeze` fails closed — so the very first `ebpy freeze` in a Python repository would refuse. It would also add `clippy was not measured and has no ceiling here.` to every `ebpy check`. Task 4 removed both.

**`freeze`'s `Unavailable` branch must stop naming `ebpy bootstrap`.** Today it prints *"Install it first: `ebpy bootstrap` is the step."* for every unavailable analyzer. There is deliberately no clippy provisioner (`plan_packages` feeds a single dev-install command, and clippy is `rustup component add`, not a dev dependency), so that sentence would send a reader to a door that opens on nothing. The fix is not a new API: the `Failed` branch already quotes `observation.detail`, and `ClippyNotFoundError`'s detail already carries the rustup hint. Quote the detail here too.

- [ ] **Step 1: Write the failing tests**

In `tests/test_tools.py`, update the two registry assertions:

```python
def test_registry_lists_the_three_analyzers_with_valid_names() -> None:
    """ANALYZERS contains exactly ruff, mypy and clippy, with valid names and non-empty nouns."""
    names = tuple(a.name for a in ANALYZERS)
    assert set(names) == {"ruff", "mypy", "clippy"}
    assert all(is_analyzer_name(a.name) for a in ANALYZERS)
    assert all(a.noun for a in ANALYZERS)
    assert set(ANALYZERS_BY_NAME) == set(names)
    assert tuple(sorted(names)) == ANALYZER_NAMES
```

and extend the language test from Task 1 to `{"ruff": "python", "mypy": "python", "clippy": "rust"}`.

Add to `tests/test_freeze.py`:

```python
def test_an_unavailable_analyzer_is_refused_with_its_own_installation_advice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ebpy bootstrap` provisions no clippy, so a fixed sentence naming it opens on nothing."""
    measurement = Measurement(
        {"clippy": Unavailable(tool="clippy", detail="run `rustup component add clippy`")}
    )
    monkeypatch.setattr(freeze, "measure_repository", lambda _cwd, _scope: measurement)
    with pytest.raises(CommandError) as caught:
        freeze.run_freeze(tmp_path, force=False, analyzer="clippy")
    assert "rustup component add clippy" in str(caught.value)
    assert "ebpy bootstrap" not in str(caught.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py tests/test_freeze.py -v`
Expected: FAIL — clippy absent from `ANALYZERS`; the refusal still says `ebpy bootstrap`

- [ ] **Step 3: Register the analyzer**

In `src/ebpy/tools/registry.py`, import `ClippyAnalyzer` from `.clippy` and extend:

```python
_registry: list[Analyzer] = [RuffAnalyzer(), MypyAnalyzer(), ClippyAnalyzer()]
```

- [ ] **Step 4: Quote the detail in `freeze`'s unavailable branch**

In `src/ebpy/commands/freeze.py`, `_refusal_reason`:

```python
    if status == "unavailable":
        assert isinstance(observation, Unavailable)
        # The observation carries how to fix it; a fixed sentence naming `ebpy bootstrap`
        # was only ever right because every analyzer used to have a provisioner. The Failed
        # branch below has always quoted the detail for the same reason.
        return "\n".join(
            [
                f"{analyzer} could not be run here:",
                *(f"  {line}" for line in observation.detail.splitlines()),
                "Do not freeze without it — a ceiling that omits an analyzer cannot be trusted.",
            ]
        )
```

Then make sure `RuffNotFoundError` and `MypyNotFoundError` details still name `ebpy bootstrap`. `RuffNotFoundError`'s message already ends *"Run `ebpy bootstrap` first."* — check mypy's and add the same sentence if it is missing, so the Python analyzers keep the guidance they had.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS. Fix any test that asserted a two-analyzer registry — `tests/test_measurement.py`'s `test_measure_repository_produces_one_observation_per_registered_analyzer` is the likely one; pass an explicit scope there.

- [ ] **Step 6: Verify the repository still gates itself**

Run: `uv run ruff format . && uv run pytest && uv run ebpy check`
Expected: PASS. `ebpy check` on this repository detects Python only, so clippy is not in scope and produces no note — which is the whole point of Task 4 landing first.

- [ ] **Step 7: Commit**

```bash
git add src/ebpy/tools/registry.py src/ebpy/commands/freeze.py tests/ && git commit -m "feat(clippy): register the analyzer and let its refusal carry its own advice"
```

---

## Task 12: The manifest and config facts a clippy detector needs

**Files:**
- Modify: `src/ebpy/repo/facts.py` (`InvalidToml`, `RepoFacts.cargo_manifests`, `RepoFacts.clippy_config_paths`, `gather_facts`)
- Test: `tests/test_detectors.py` (or a new `tests/test_facts.py` if that file has no facts section)

**Interfaces:**
- Produces:
  - `InvalidToml(path: PurePosixPath, detail: str)`
  - `RepoFacts.cargo_manifests: Mapping[PurePosixPath, dict[str, Any] | InvalidToml]`
  - `RepoFacts.clippy_config_paths: tuple[PurePosixPath, ...]`

**Why the facts and not the detector read these files.** `RepoFacts`'s own contract is *"Everything read from disk once, so decisions stay pure."* A detector opening files itself breaks it.

**Five rules that matter:**
1. **Read TOML through `ebpy._toml`, not `tomllib`.** `facts.py` already does (`from ebpy._toml import TOMLDecodeError, loads`); a direct `import tomllib` here would pass on the developer's interpreter and fail the 3.10 leg of the CI matrix.
2. **Catch `UnicodeError` alongside `OSError` and `TOMLDecodeError`.** `read_text(encoding="utf-8")` raises `UnicodeDecodeError` on invalid UTF-8, which is neither of the other two. Catching only two means one badly-encoded `Cargo.toml` makes `gather_facts` raise and *every* ebpy command in that repository stop working. (The same hole exists today in the `pyproject.toml` read — noted so the new code does not copy it, but fixing it is unrelated work.)
3. **A manifest that could not be read is `InvalidToml`, never `configured=False`.** "clippy is not configured" and "ebpy could not read the file" must not render identically.
4. **`detail` never contains an absolute path.** The diagnosis is persisted into the ledger and `QUALITY.md`; `str(OSError)` would bake this host's directory layout into a committed artifact. Take `error.strerror` (falling back to the exception class name), the codec error's reason and offset, or `str(TOMLDecodeError)` — which carries line and column but no path. Files are always named by `InvalidToml.path`, repository-relative.
5. **The same `target`-segment exclusion the runner uses.** Otherwise the detector names a generated manifest broken that the runner never looked at.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_cargo_manifest_is_parsed_into_the_facts(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[lints.clippy]\nall = 'warn'\n", encoding="utf-8")
    facts = gather_facts(tmp_path)
    manifest = facts.cargo_manifests[PurePosixPath("Cargo.toml")]
    assert isinstance(manifest, dict)
    assert manifest["lints"]["clippy"] == {"all": "warn"}


def test_an_unparseable_manifest_is_recorded_rather_than_flattened_to_false(tmp_path: Path) -> None:
    """"no clippy config" and "ebpy could not read the file" are different facts."""
    (tmp_path / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    manifest = gather_facts(tmp_path).cargo_manifests[PurePosixPath("Cargo.toml")]
    assert isinstance(manifest, InvalidToml)
    assert manifest.path == PurePosixPath("Cargo.toml")


def test_a_badly_encoded_manifest_does_not_stop_every_command(tmp_path: Path) -> None:
    """UnicodeDecodeError is neither OSError nor TOMLDecodeError; missing it breaks gather_facts."""
    (tmp_path / "Cargo.toml").write_bytes(b"[package]\nname = '\xff\xfe'\n")
    manifest = gather_facts(tmp_path).cargo_manifests[PurePosixPath("Cargo.toml")]
    assert isinstance(manifest, InvalidToml)


def test_an_invalid_manifest_detail_never_carries_a_host_path(tmp_path: Path) -> None:
    """The diagnosis is persisted, so an absolute path would be baked into a committed artifact."""
    (tmp_path / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    manifest = gather_facts(tmp_path).cargo_manifests[PurePosixPath("Cargo.toml")]
    assert isinstance(manifest, InvalidToml)
    assert str(tmp_path) not in manifest.detail


def test_clippy_config_files_are_listed_in_ascending_order(tmp_path: Path) -> None:
    (tmp_path / "crates").mkdir()
    (tmp_path / ".clippy.toml").write_text("", encoding="utf-8")
    (tmp_path / "crates" / "clippy.toml").write_text("", encoding="utf-8")
    assert gather_facts(tmp_path).clippy_config_paths == (
        PurePosixPath(".clippy.toml"),
        PurePosixPath("crates/clippy.toml"),
    )


def test_a_manifest_under_a_target_segment_is_not_a_fact(tmp_path: Path) -> None:
    """The detector must not call a manifest broken that the runner never looked at."""
    generated = tmp_path / "target" / "package" / "a-0.1.0"
    generated.mkdir(parents=True)
    (generated / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    assert gather_facts(tmp_path).cargo_manifests == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_detectors.py -v`
Expected: FAIL with `ImportError: cannot import name 'InvalidToml'`

- [ ] **Step 3: Add `InvalidToml` and the fields**

In `src/ebpy/repo/facts.py`:

```python
@dataclass(frozen=True)
class InvalidToml:
    """A manifest ebpy could not read, and why — kept apart from a manifest with no clippy config.

    `detail` never carries an absolute path. This value ends up in the diagnosis, which is
    written to the ledger and to QUALITY.md, and `str(OSError)` would bake this host's
    directory layout into a committed artifact. The file is named by `path` instead.
    """

    path: PurePosixPath
    detail: str
```

and on `RepoFacts`:

```python
    # Cargo manifests, parsed once. A value that is InvalidToml means the file exists and
    # could not be read — which is not the same as a manifest with no clippy configuration.
    cargo_manifests: Mapping[PurePosixPath, dict[str, Any] | InvalidToml] = field(default_factory=dict)
    # clippy.toml / .clippy.toml, ascending. Existence only; the contents are never read.
    clippy_config_paths: tuple[PurePosixPath, ...] = ()
```

Both need defaults, because `RepoFacts` is constructed positionally in tests. Add `Mapping` to the `collections.abc` import.

- [ ] **Step 4: Read them in `gather_facts`**

```python
_CLIPPY_CONFIG_NAMES = ("clippy.toml", ".clippy.toml")


def _toml_failure(error: Exception) -> str:
    """Describe a TOML read failure without naming this host's filesystem."""
    if isinstance(error, OSError):
        return error.strerror or type(error).__name__
    if isinstance(error, UnicodeDecodeError):
        return f"invalid {error.encoding} at byte {error.start}: {error.reason}"
    return str(error)


def _read_cargo_manifests(cwd: Path, all_files: list[str]) -> dict[PurePosixPath, dict[str, Any] | InvalidToml]:
    manifests: dict[PurePosixPath, dict[str, Any] | InvalidToml] = {}
    for file in sorted(all_files):
        path = PurePosixPath(file)
        if path.name != "Cargo.toml" or "target" in path.parts[:-1]:
            continue
        try:
            manifests[path] = loads((cwd / file).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, TOMLDecodeError) as error:
            # UnicodeError belongs here: read_text raises UnicodeDecodeError on invalid UTF-8,
            # which is neither of the other two, and letting it escape would stop every ebpy
            # command in the repository rather than just this one file's detection.
            manifests[path] = InvalidToml(path=path, detail=_toml_failure(error))
    return manifests
```

and in `gather_facts`, before the `return`:

```python
    cargo_manifests = _read_cargo_manifests(cwd, all_files)
    clippy_config_paths = tuple(
        PurePosixPath(file)
        for file in sorted(all_files)
        if PurePosixPath(file).name in _CLIPPY_CONFIG_NAMES and "target" not in PurePosixPath(file).parts[:-1]
    )
```

passing both into the `RepoFacts(...)` call.

- [ ] **Step 5: Run tests**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 6: Format and commit**

```bash
git add src/ebpy/repo/facts.py tests/test_detectors.py && git commit -m "feat(facts): read Cargo manifests and clippy config paths once"
```

---

## Task 13: `ClippyDetector` — clippy's configuration, never Rust's existence

**Files:**
- Create: `src/ebpy/tools/clippy/detector.py`
- Modify: `src/ebpy/tools/clippy/__init__.py`, `src/ebpy/tools/registry.py` (`_detectors`)
- Test: `tests/test_detectors.py`

**Interfaces:**
- Consumes: `RepoFacts.cargo_manifests`, `RepoFacts.clippy_config_paths` (Task 12).
- Produces: `ClippySetup(ToolSetup)` with `invalid_manifests: tuple[InvalidToml, ...]`; `ClippyDetector` with `name="clippy"`.

**What `configured` may claim, and what it may not.** `ToolSetup.configured` asserts *"this repository configured this tool"*. `Cargo.toml` existing asserts *"this repository contains Rust"* — a different claim, and folding it in re-merges exactly what Task 2 separated. The "Rust is here but clippy is unratcheted" gap comes from language detection and the frozen roster instead (Task 15).

**Detection rules:**

| target | rule |
| --- | --- |
| `clippy.toml` / `.clippy.toml` | present in an **ancestor directory of some Cargo manifest** → `configured=True`. Contents never read. |
| `[lints.clippy]` / `[workspace.lints.clippy]` | counted only when the value is a `dict`. |
| CI / pre-commit | `\bcargo(?:\s+\+\S+)?\s+clippy\b`, case-sensitive. |

- The ancestor rule is an approximation of Clippy's own search (`CLIPPY_CONF_DIR` → `CARGO_MANIFEST_DIR` → cwd, walking up). "Any `clippy.toml` anywhere" would let one file under `tests/fixtures/` mark the whole repository configured.
- `+toolchain` must be matched: `cargo +nightly clippy` is a normal CI spelling that a naive `cargo\s+clippy` misses.
- Comment lines are **not** excluded. `detect_ci` already uses regexes over raw YAML, and parsing here would make two rules say different things about one repository.
- `gaps()` reports **only** unreadable manifests, one gap each. There is deliberately no "clippy is not configured" gap: clippy runs with no repository configuration and has no provisioner, so such a gap would have no way to be closed — and it would duplicate Task 15's unratcheted gap.
- `configured=True` and an invalid manifest coexist happily; the gaps are independent of `configured`.
- No `from_dict`. The ledger reads every setup back as a base `ToolSetup` by design (`models.diagnosis_from_dict`), exactly as `MypySetup` is treated.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_cargo_manifest_alone_does_not_make_clippy_configured(tmp_path: Path) -> None:
    """`configured` claims the repository configured clippy, not that it contains Rust."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert not ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_lint_table_makes_clippy_configured(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[lints.clippy]\nall='warn'\n", encoding="utf-8")
    assert ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_workspace_lint_table_makes_clippy_configured(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[workspace.lints.clippy]\nall='warn'\n", encoding="utf-8")
    assert ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_clippy_toml_above_a_manifest_makes_clippy_configured(tmp_path: Path) -> None:
    (tmp_path / "clippy.toml").write_text("msrv = '1.79'\n", encoding="utf-8")
    (tmp_path / "crates" / "a").mkdir(parents=True)
    (tmp_path / "crates" / "a" / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_clippy_toml_below_every_manifest_does_not_configure_the_repository(tmp_path: Path) -> None:
    """One fixture file must not mark a whole repository configured."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "clippy.toml").write_text("", encoding="utf-8")
    assert not ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_ci_step_running_clippy_makes_it_configured(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("jobs:\n  a:\n    steps:\n      - run: cargo clippy\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_a_toolchain_qualified_ci_step_is_recognised(tmp_path: Path) -> None:
    """`cargo +nightly clippy` is a normal CI spelling a naive regex misses."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("      - run: cargo +nightly clippy -- -D warnings\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert ClippyDetector().detect(gather_facts(tmp_path)).configured


def test_an_unreadable_manifest_is_named_in_its_own_gap(tmp_path: Path) -> None:
    """Aggregating them into one gap makes it impossible to see which are still broken."""
    (tmp_path / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    (tmp_path / "crates").mkdir()
    (tmp_path / "crates" / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    gaps = ClippyDetector().gaps(ClippyDetector().detect(gather_facts(tmp_path)))
    assert [g.id for g in gaps] == ["clippy-manifest:Cargo.toml", "clippy-manifest:crates/Cargo.toml"]


def test_an_unconfigured_clippy_reports_no_gap_at_all(tmp_path: Path) -> None:
    """clippy needs no repository configuration and has no provisioner, so such a gap cannot close."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert ClippyDetector().gaps(ClippyDetector().detect(gather_facts(tmp_path))) == []


def test_an_invalid_manifest_and_a_configured_clippy_coexist(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[lints.clippy]\nall='warn'\n", encoding="utf-8")
    (tmp_path / "crates").mkdir()
    (tmp_path / "crates" / "Cargo.toml").write_text("[lints.clippy\n", encoding="utf-8")
    setup = ClippyDetector().detect(gather_facts(tmp_path))
    assert setup.configured
    assert len(setup.invalid_manifests) == 1


def test_the_clippy_row_says_it_runs_without_configuration(tmp_path: Path) -> None:
    """Unlike the other six tools, clippy still works unconfigured; the row must not imply otherwise."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    row = ClippyDetector().render_row(ClippyDetector().detect(gather_facts(tmp_path)))
    assert "runs with defaults" in row
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_detectors.py -v`
Expected: FAIL with `ImportError: cannot import name 'ClippyDetector'`

- [ ] **Step 3: Write the detector**

Create `src/ebpy/tools/clippy/detector.py`:

```python
"""clippy configuration detection: the setup value, its detection, and the gaps it reports.

`configured` claims one thing only — that this repository configured clippy. `Cargo.toml`
existing claims something else, that the repository contains Rust, and folding the second
into the first would put language detection back inside a detector. The "Rust is here but
clippy holds no ceiling" proposal comes from language detection and the frozen roster.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ebpy.models import Gap, ToolSetup
from ebpy.repo.facts import InvalidToml

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import PurePosixPath

    from ebpy.repo.facts import RepoFacts

# `+toolchain` between the two words is a spelling rustup supports and CI files use;
# `cargo\s+clippy` alone silently misses `cargo +nightly clippy`. Case-sensitive, because
# cargo's subcommands are lowercase. Comment lines are deliberately not excluded: `detect_ci`
# already matches raw YAML with regexes, and parsing here would make two rules disagree
# about one repository.
_CLIPPY_INVOCATION = re.compile(r"\bcargo(?:\s+\+\S+)?\s+clippy\b")


@dataclass(frozen=True)
class ClippySetup(ToolSetup):
    """Detection result for clippy, extending ToolSetup with the manifests it could not read."""

    invalid_manifests: tuple[InvalidToml, ...]


def _lint_table_present(manifest: dict[str, Any]) -> bool:
    for table in (manifest.get("lints"), (manifest.get("workspace") or {}).get("lints")):
        if isinstance(table, dict) and isinstance(table.get("clippy"), dict):
            return True
    return False


def _config_covers_a_manifest(
    config_paths: tuple[PurePosixPath, ...], manifests: Mapping[PurePosixPath, object]
) -> bool:
    """Whether a clippy config sits above some Cargo manifest.

    An approximation of Clippy's own search, which walks up from CLIPPY_CONF_DIR, the manifest
    directory, and the cwd. ebpy does not reproduce the environment variables, so it stops at
    "in an ancestor of a manifest" — and says so rather than claiming to know what Clippy will
    read. The naive "any clippy.toml anywhere" would let one file under tests/fixtures/ mark a
    whole repository configured.
    """
    directories = {manifest.parent for manifest in manifests}
    return any(
        config.parent == directory or config.parent in directory.parents
        for config in config_paths
        for directory in directories
    )


@dataclass(frozen=True)
class ClippyDetector:
    """Detects whether clippy is configured and reports the manifests it could not read."""

    @property
    def name(self) -> str:
        """Unique short identifier for clippy."""
        return "clippy"

    def detect(self, facts: RepoFacts) -> ClippySetup:
        """Return clippy's configuration state, keeping unreadable manifests apart from absent ones."""
        invalid = tuple(
            manifest
            for _, manifest in sorted(facts.cargo_manifests.items())
            if isinstance(manifest, InvalidToml)
        )
        text = "\n".join(
            [
                *(workflow.content for workflow in facts.workflows),
                facts.extra_config_text.get(".pre-commit-config.yaml") or "",
            ]
        )
        configured = (
            _config_covers_a_manifest(facts.clippy_config_paths, facts.cargo_manifests)
            or any(
                _lint_table_present(manifest)
                for manifest in facts.cargo_manifests.values()
                if isinstance(manifest, dict)
            )
            or _CLIPPY_INVOCATION.search(text) is not None
        )
        return ClippySetup(configured=configured, invalid_manifests=invalid)

    def gaps(self, setup: ClippySetup) -> list[Gap]:
        """Name each manifest that could not be read. Being unconfigured is not a gap.

        clippy runs with no repository configuration (so there is nothing to install) and has
        no provisioner, so a "not configured" gap would have no way to be closed — and it
        would say the same thing as the unratcheted gap already does. One gap per manifest,
        not one aggregate: after fixing two of three, a reader has to see which is left.
        """
        return [
            Gap(
                id=f"clippy-manifest:{manifest.path}",
                title=f"{manifest.path} could not be read as TOML",
                detail=f"{manifest.detail} — clippy's configuration in this file was not counted.",
                phase="tighten",
            )
            for manifest in setup.invalid_manifests
        ]

    def render_row(self, setup: ClippySetup) -> str:
        """Render a one-line clippy row for the diagnosis table."""
        # The parenthetical is here because clippy is the one tool of the seven that still
        # works unconfigured, which changes what "no" means on this row alone.
        state = "configured" if setup.configured else "not configured (runs with defaults)"
        return f"  clippy            {state}"
```

- [ ] **Step 4: Register it last**

In `src/ebpy/tools/registry.py`, append `ClippyDetector()` to `_detectors`. **Last**, because registry order is the CLI's display order everywhere and the existing six must not move.

Also update the comment above `_provisioners` — `Order matches DETECTORS` stops being true the moment a detector has no provisioner:

```python
# Order follows DETECTORS for the tools that have one. The correspondence is no longer
# one-to-one: clippy has a detector and deliberately no provisioner, because provisioning it
# is `rustup component add`, not a dev dependency the plan's single install command can carry.
```

Export `ClippyDetector` and `ClippySetup` from `src/ebpy/tools/clippy/__init__.py`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest -v`
Expected: FAIL in `tests/test_tools.py` (`test_detectors_registry_lists_all_tools` still expects six) — update it to include `"clippy"`, then re-run. Also expect `tests/test_diagnose.py` / `tests/test_render.py` failures if any assert the exact diagnosis row list; add the clippy row there.

- [ ] **Step 6: Format and commit**

```bash
git add src/ebpy/tools/clippy/ src/ebpy/tools/registry.py tests/ && git commit -m "feat(clippy): detect clippy's own configuration without claiming Rust's presence"
```

---

## Task 14: Detectors are filtered by language

**Files:**
- Modify: `src/ebpy/repo/detect/detector.py` (`ToolDetector.languages`)
- Modify: all seven detectors (`tools/ruff/detector.py`, `tools/ruff_format.py`, `tools/mypy/detector.py`, `tools/pytest.py`, `tools/vulture.py`, `tools/gitleaks.py`, `tools/clippy/detector.py`)
- Modify: `src/ebpy/decide/diagnose.py` (`diagnose` signature and detector loops)
- Modify: `src/ebpy/render/report.py:21`
- Modify: `src/ebpy/commands/diagnose.py`, `src/ebpy/commands/bootstrap.py`
- Test: `tests/test_diagnose.py`, `tests/test_detectors.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: `languages_from_files` (Task 2); `Language` (Task 1).
- Produces: `ToolDetector.languages -> frozenset[Language]`; `diagnose(facts, frozen_analyzers, languages: frozenset[Language]) -> Diagnosis`.

**The roster:**

| detector | `languages` |
| --- | --- |
| `ruff`, `formatter`, `mypy`, `pytest`, `vulture` | `frozenset({"python"})` |
| `secret-scan` | `frozenset()` — repository-wide, always runs |
| `clippy` | `frozenset({"rust"})` |

**Detectors go plural from the start while analyzers stay singular.** *"Do not abstract until the second implementation exists"* applies to both, and for detectors it already does: `GitleaksDetector` reads workflows, pre-commit config and `.gitleaks.toml` and depends on no language. Making it return `{"python"}` would make its name assert something false.

**The `render/report.py:21` `KeyError`.** It indexes `diagnosis.tool_setups[detector.name]` while iterating all of `DETECTORS`; with a filtered map that raises. Fix by **iterating `DETECTORS` and testing membership** — not by iterating the map's keys. `diagnosis_from_dict` reads back whatever keys the ledger holds, so a future ebpy's unknown key would make a `DETECTORS_BY_NAME[name]` lookup raise; and only iterating the registry preserves registry order as display order.

`render/quality.py:151` uses `if name in setups` already and needs no change.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_python_only_repository_gets_no_clippy_setup(tmp_path: Path) -> None:
    """A Cargo-less repository must not carry a permanent, uncloseable clippy row and gap."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    facts = gather_facts(tmp_path)
    diagnosis = diagnose(facts, (), frozenset({"python"}))
    assert "clippy" not in diagnosis.tool_setups
    assert "ruff" in diagnosis.tool_setups


def test_secret_scanning_runs_in_every_repository(tmp_path: Path) -> None:
    """It reads workflows and pre-commit config; claiming it belongs to Python would be false."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    diagnosis = diagnose(gather_facts(tmp_path), (), frozenset({"rust"}))
    assert "secret-scan" in diagnosis.tool_setups
    assert "ruff" not in diagnosis.tool_setups


def test_the_diagnosis_renders_without_a_key_for_every_detector(tmp_path: Path) -> None:
    """render/report.py indexes the setup map; a filtered map makes that a KeyError."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    output = render_diagnosis(diagnose(gather_facts(tmp_path), (), frozenset({"python"})))
    assert "clippy" not in output


def test_the_diagnosis_renders_an_unknown_stored_setup_without_raising() -> None:
    """The ledger reads back whatever keys it holds, including a future ebpy's unknown tool."""
    diagnosis = diagnosis_from_dict({"toolSetups": {"pylint": {"configured": True}}})
    assert render_diagnosis(diagnosis)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_diagnose.py -v`
Expected: FAIL — `diagnose() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Add the Protocol member**

In `src/ebpy/repo/detect/detector.py`, import `Language` under `TYPE_CHECKING` and add:

```python
    @property
    def languages(self) -> frozenset[Language]:
        """The languages this detector's tool belongs to; empty means repository-wide."""
        ...
```

Plural from the start, unlike `Analyzer.language`: a language-independent detector already exists here (`secret-scan`), so the abstraction is not speculative.

- [ ] **Step 4: Declare it on all seven detectors**

For each of the six Python-and-repository detectors, add a property beside `name`:

```python
    @property
    def languages(self) -> frozenset[Language]:
        """ruff is a Python tool."""
        return frozenset({"python"})
```

For `GitleaksDetector`:

```python
    @property
    def languages(self) -> frozenset[Language]:
        """Empty: secret scanning reads workflows and pre-commit config, not source in any language."""
        return frozenset()
```

For `ClippyDetector`: `return frozenset({"rust"})`.

Import `Language` at module scope in each (property return annotations are fine under `TYPE_CHECKING`, so the existing block will do where one exists).

- [ ] **Step 5: Filter inside `diagnose`**

In `src/ebpy/decide/diagnose.py`:

```python
def diagnose(
    facts: RepoFacts, frozen_analyzers: tuple[str, ...], languages: frozenset[Language]
) -> Diagnosis:
    """Survey the repository, naming every gap.

    `frozen_analyzers` is the roster the ledger already holds — empty for a repository that
    has never frozen. `languages` narrows the detectors that run: a Cargo-less repository
    would otherwise carry a permanent clippy row and a gap with no way to close it.
    """
    detectors = tuple(d for d in DETECTORS if not d.languages or d.languages & languages)
    tool_setups = {detector.name: detector.detect(facts) for detector in detectors}
    ...
    gaps = [
        *(gap for detector in detectors for gap in detector.gaps(tool_setups[detector.name])),
        ...
    ]
```

Both loops use the same filtered tuple.

- [ ] **Step 6: Fix the renderer**

In `src/ebpy/render/report.py`:

```python
    # Iterating DETECTORS rather than the setup map's keys: registry order is the display
    # order, and the ledger reads back whatever keys it holds — a future ebpy's unknown tool
    # would make a DETECTORS_BY_NAME lookup raise on a file this one can otherwise read.
    detector_rows = [
        detector.render_row(diagnosis.tool_setups[detector.name])
        for detector in DETECTORS
        if detector.name in diagnosis.tool_setups
    ]
```

- [ ] **Step 7: Pass languages from both callers**

`src/ebpy/commands/diagnose.py`:

```python
    facts = gather_facts(cwd)
    languages = languages_from_files(facts.all_files)
    diagnosis = diagnose(facts, frozen_analyzers, languages.languages)
```

`src/ebpy/commands/bootstrap.py`:

```python
    facts = gather_facts(cwd)
    languages = languages_from_files(facts.all_files)
    diagnosis = diagnose(facts, (), languages.languages)
```

Both use `languages_from_files(facts.all_files)`, not `detect_languages(cwd)`: they have already listed the tree, and `RepoFacts`'s contract is that the read happens once.

- [ ] **Step 8: Run tests**

Run: `uv run pytest -v`
Expected: PASS after updating any `diagnose(facts, ())` call sites in tests to pass a third argument.

- [ ] **Step 9: Format and commit**

```bash
git add src/ebpy/repo/detect/detector.py src/ebpy/tools/ src/ebpy/decide/diagnose.py src/ebpy/render/report.py src/ebpy/commands/diagnose.py src/ebpy/commands/bootstrap.py tests/ && git commit -m "feat(diagnose): run only the detectors whose language the repository has"
```

---

## Task 15: The unratcheted gap, and the marker that follows it

**Files:**
- Modify: `src/ebpy/repo/detect/detector.py` (`requires_repository_setup`) and all seven detectors
- Modify: `src/ebpy/decide/diagnose.py` (`_unratcheted_gaps`)
- Modify: `src/ebpy/render/quality.py` (`_unratcheted_marker`)
- Test: `tests/test_diagnose.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: `ToolDetector.languages` (Task 14).
- Produces: `ToolDetector.requires_repository_setup -> bool` (`True` for the six, `False` for clippy); `_unratcheted_gaps(tool_setups, frozen_analyzers, languages)`.

**Why one flag and not just "the language matches".** With Task 13 removing `Cargo.toml` from `configured`, a Rust repository with no `clippy.toml` reports `configured=False` and today's condition emits nothing — precisely the mixed-repository case the whole feature exists for. But loosening the condition to "language matches" alone makes an unconfigured Python repository emit *"ruff is configured but not ratcheted"*, duplicating the existing "Ruff is not configured" bootstrap gap and advising a `ebpy freeze --analyzer ruff` that fails because ruff is not installed.

**The name states ebpy's policy, not the tool's nature.** ruff and mypy also run without a config file, so `requires_repository_configuration` returning `True` for ruff would be a false claim. What is true is: *ebpy waits for the repository to have adopted ruff — via bootstrap or a detected config — before proposing to ratchet it.* clippy has no adoption step at all (no provisioner, nothing to install into the repository), so the language's presence is enough. `runs_unconfigured` would be wrong for a different reason: whether clippy actually runs depends on the toolchain, and `diagnose` never probes.

**The `setup is None` guard must survive.** After Task 14, `tool_setups` is filtered — a Python-only repository has **no** clippy setup. Today's code guards with `tool_setups.get(name)` and `setup is not None`; replacing only the boolean expression deletes that guard and produces `AttributeError`.

**The `QUALITY.md` marker moves to the gaps.** `_unratcheted_marker` builds from `setups[name].configured`, so a Rust repository with no `clippy.toml` has the gap in Outstanding but nothing in the heading. Build it from `state.diagnosis.gaps` where `id` starts with `unratcheted:` instead — the gaps are already in the ledger, so no language information needs storing. **Re-filter against the current roster**: `diagnosis` is a snapshot of the last `diagnose`, so an analyzer frozen since still has its gap, and without the re-filter it reads as unratcheted until the next `diagnose`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_rust_repository_without_a_clippy_config_is_still_offered_the_ratchet(tmp_path: Path) -> None:
    """This is the mixed-repository case the whole feature exists for."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    gaps = diagnose(gather_facts(tmp_path), (), frozenset({"rust"})).gaps
    assert "unratcheted:clippy" in {g.id for g in gaps}


def test_an_unconfigured_ruff_is_not_offered_the_ratchet(tmp_path: Path) -> None:
    """`ebpy freeze --analyzer ruff` would fail: ruff is not installed, so the advice is unusable."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    gaps = diagnose(gather_facts(tmp_path), (), frozenset({"python"})).gaps
    assert "unratcheted:ruff" not in {g.id for g in gaps}


def test_a_frozen_clippy_produces_no_unratcheted_gap(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    gaps = diagnose(gather_facts(tmp_path), ("clippy",), frozenset({"rust"})).gaps
    assert "unratcheted:clippy" not in {g.id for g in gaps}


def test_a_python_only_repository_does_not_crash_on_a_missing_clippy_setup(tmp_path: Path) -> None:
    """After the language filter there is no clippy setup at all; the None guard is what saves it."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert diagnose(gather_facts(tmp_path), (), frozenset({"python"})).gaps is not None


def test_the_quality_marker_names_a_language_derived_unratcheted_analyzer() -> None:
    """Building the marker from `configured` leaves the heading silent while Outstanding lists it."""
    diagnosis = _diagnosis_with_gaps([Gap(id="unratcheted:clippy", title="t", detail="d", phase="tighten")])
    state = State(frozen_analyzers=("ruff",), diagnosis=diagnosis)
    assert "clippy" in render_quality_file(state)


def test_the_quality_marker_clears_as_soon_as_the_analyzer_is_frozen() -> None:
    """The diagnosis is last-run's snapshot; without a re-filter the note lingers until the next one."""
    diagnosis = _diagnosis_with_gaps([Gap(id="unratcheted:clippy", title="t", detail="d", phase="tighten")])
    state = State(frozen_analyzers=("clippy", "ruff"), diagnosis=diagnosis)
    assert "is configured but not ratcheted" not in render_quality_file(state)
```

(`_diagnosis_with_gaps` is a small local helper building a `Diagnosis` with default fields and the given gaps; `render_quality_file` is whatever `render/quality.py` exposes — check its actual public name.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_diagnose.py tests/test_render.py -v`
Expected: FAIL — no `unratcheted:clippy` gap; the marker misses it

- [ ] **Step 3: Add the second Protocol member**

In `src/ebpy/repo/detect/detector.py`, beside `languages`:

```python
    @property
    def requires_repository_setup(self) -> bool:
        """Whether ebpy requires repository-side setup before proposing this tool for ratcheting.

        A statement of ebpy's policy, not of the tool's nature: ruff and mypy both run without
        a config file, so a name asserting they need one would be false. What is true is that
        ebpy waits for a repository to have adopted them — through bootstrap or a detected
        config — before proposing a ceiling. clippy has no adoption step to wait for.
        """
        ...
```

Return `True` from the six existing detectors, `False` from `ClippyDetector`.

- [ ] **Step 4: Rewrite the gap condition**

In `src/ebpy/decide/diagnose.py`:

```python
def _unratcheted_gaps(
    tool_setups: dict[str, ToolSetup],
    frozen_analyzers: tuple[str, ...],
    languages: frozenset[Language],
) -> list[Gap]:
    """Report a gap per analyzer this repository could ratchet but the frozen contract omits.

    Two routes to a proposal, because ebpy has two policies. For ruff and mypy it waits until
    the repository adopted the tool, so an unconfigured one gets a bootstrap gap instead —
    proposing a freeze there would advise a command that fails, since the tool is not
    installed. clippy needs no adoption, so the language's presence is the whole condition.
    """
    roster = set(frozen_analyzers)
    gaps: list[Gap] = []
    for name in ANALYZERS_BY_NAME:
        if name in roster:
            continue
        setup = tool_setups.get(name)
        # Absent whenever the language filter dropped this detector — a Python-only
        # repository holds no clippy setup at all.
        if setup is None:
            continue
        detector = DETECTORS_BY_NAME[name]
        if setup.configured:
            title = f"{name} is configured but not ratcheted"
            detail = (
                f"{name} runs in this repository but is not in the frozen contract, so its "
                f"findings hold no ceiling. `ebpy freeze --analyzer {name}` pins them."
            )
        elif not detector.requires_repository_setup and detector.languages & languages:
            title = f"{name} can ratchet this repository but is not in the contract"
            detail = (
                f"{name} needs no configuration here, and what it measures is present, but it "
                f"holds no ceiling. `ebpy freeze --analyzer {name}` pins today's findings."
            )
        else:
            continue
        gaps.append(Gap(id=f"unratcheted:{name}", title=title, detail=detail, phase="tighten"))
    return gaps
```

Import `DETECTORS_BY_NAME` alongside `ANALYZERS_BY_NAME` and `DETECTORS`. The loop still walks `ANALYZERS_BY_NAME` — only an analyzer can be ratcheted — and the registry uses the same name on both sides (`tools/registry.py:57`), which is what makes the `DETECTORS_BY_NAME[name]` lookup valid.

Pass `languages` through from `diagnose(...)` at the call site.

- [ ] **Step 5: Rebuild the quality marker from the gaps**

In `src/ebpy/render/quality.py`:

```python
def _unratcheted_marker(state: State, roster: set[str]) -> str:
    """Name an analyzer the repository could ratchet but the frozen contract omits.

    Read from the diagnosis's gaps rather than rebuilt from `configured`: after clippy, a
    repository can earn this gap from its language alone, and a marker derived from
    `configured` would leave the heading silent while Outstanding lists it. Skipped with no
    diagnosis at all — inventing a complaint from missing data is what "absence and zero are
    different" forbids.
    """
    if state.diagnosis is None:
        return ""
    # Re-filtered against today's roster: the diagnosis is the last `diagnose`'s snapshot, so
    # an analyzer frozen since then still carries its gap and would read as unratcheted until
    # somebody ran `diagnose` again.
    unratcheted = sorted(
        suffix
        for gap in state.diagnosis.gaps
        if gap.id.startswith("unratcheted:")
        and (suffix := gap.id.removeprefix("unratcheted:"))
        and suffix not in roster
    )
    if not unratcheted:
        return ""
    return " (" + ", ".join(f"{analyzer} is not ratcheted" for analyzer in unratcheted) + ")"
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest -v`
Expected: PASS. Any test asserting the old marker wording (*"is configured but not ratcheted"*) needs updating to the new *"is not ratcheted"*, which is the phrasing that stays true for both routes.

- [ ] **Step 7: Format and commit**

```bash
git add src/ebpy/repo/detect/detector.py src/ebpy/tools/ src/ebpy/decide/diagnose.py src/ebpy/render/quality.py tests/ && git commit -m "feat(diagnose): propose clippy from the language when no setup step exists"
```

---

## Task 16: The ledger remembers what the contract does not cover

**Files:**
- Modify: `src/ebpy/models.py` (`State.unmeasured_packages`)
- Modify: `src/ebpy/store/state.py` (`_valid_unmeasured_packages`, `_has_valid_v2_shape`, `state_from_dict`, `state_to_dict`)
- Test: `tests/test_state.py`

**Interfaces:**
- Produces: `State.unmeasured_packages: tuple[str, ...] = ()`, serialized as `"unmeasuredPackages"`.

**Why the ledger and not the baseline.** `write_cells` drops cells whose count is zero (`store/baseline.py:120-136`), so **a workspace that was measured and found clean is indistinguishable in the baseline from one that was never measured**. And zero is the state ebpy is driving every repository toward, so this is the mainline, not an edge. The ledger already answers the analyzer-shaped version of this question — `frozen_analyzers` exists because *"Cells alone cannot distinguish 'the analyzer ran and found no violations' from 'the analyzer never ran'"* (`models.py:268-271`). This is the same question one level finer. No new concept.

**Package directories, not workspace roots.** A workspace root can stay identical while `members` and `exclude` move packages across it — an ordinary Cargo refactor. Comparing roots would let a package silently leave the ceiling's coverage. And it is *unmeasured* packages that are remembered, not measured ones: remembering the measured set would demand a `--force` every time a crate is deleted.

**No schema bump.** `_has_valid_v2_shape` rejects no unknown key (it names only the retired `counters`), and clippy is new, so no clippy ledger without the key can exist. There is no migration.

**Accepting unknown keys is not a licence to skip validating a known one.** Validate exactly as strictly as `_valid_frozen_analyzers` does — and on failure invalidate the whole ledger, because this key states part of the contract.

| state | treatment |
| --- | --- |
| absent | `()`. The default, not an error. |
| `list[str]`, each non-empty, no duplicates, repository-relative (no leading `/`, no `..` segment) | accepted |
| anything else | **the whole ledger is invalid** |

- [ ] **Step 1: Write the failing tests**

```python
def test_the_unmeasured_package_set_round_trips_through_the_ledger() -> None:
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    assert state_to_dict(state)["unmeasuredPackages"] == ["fuzz"]


def test_a_ledger_without_the_key_reads_as_an_empty_set() -> None:
    """Absent is the default and never an error: no clippy ledger predates the key."""
    raw = state_to_dict(State(frozen_analyzers=("ruff",)))
    del raw["unmeasuredPackages"]
    restored = state_from_dict(raw)
    assert restored is not None
    assert restored.unmeasured_packages == ()


def test_the_schema_version_does_not_move_for_the_new_key() -> None:
    assert state_to_dict(State())["version"] == 2


@pytest.mark.parametrize(
    "value",
    ["fuzz", ["fuzz", "fuzz"], [7], ["/abs/fuzz"], ["../outside"], [""]],
)
def test_a_malformed_unmeasured_package_set_invalidates_the_whole_ledger(value: object) -> None:
    """This key states part of the contract, so ebpy does not half-read it."""
    raw = state_to_dict(State(frozen_analyzers=("clippy",)))
    raw["unmeasuredPackages"] = value
    assert state_from_dict(raw) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL — `State` has no `unmeasured_packages`; `state_to_dict` writes no such key

- [ ] **Step 3: Add the field**

In `src/ebpy/models.py`, directly under `frozen_analyzers`:

```python
    # The package-level counterpart to frozen_analyzers, and there for the same reason.
    # `write_cells` drops zero-count cells, so a workspace measured and found clean looks
    # exactly like one never measured — and clean is where every repository is headed.
    # Unmeasured packages are remembered rather than measured ones so that deleting a crate
    # does not read as the contract narrowing.
    unmeasured_packages: tuple[str, ...] = ()
```

- [ ] **Step 4: Validate and serialize**

In `src/ebpy/store/state.py`, beside `_valid_frozen_analyzers`:

```python
def _valid_unmeasured_packages(value: object) -> TypeGuard[list[str]]:
    """Same strictness as the roster: a key that states the contract is never half-read."""
    if value is None:
        return True
    return (
        isinstance(value, list)
        and all(
            isinstance(package, str)
            and bool(package)
            and not package.startswith("/")
            and ".." not in PurePosixPath(package).parts
            for package in value
        )
        and len(set(value)) == len(value)
    )
```

Add `from pathlib import PurePosixPath` if it is not already imported. In `_has_valid_v2_shape`, add `and _valid_unmeasured_packages(raw.get("unmeasuredPackages"))`. In `state_from_dict`, add `unmeasured_packages=tuple(raw.get("unmeasuredPackages") or ())`. In `state_to_dict`, add `"unmeasuredPackages": sorted(state.unmeasured_packages),` next to `"frozenAnalyzers"`.

Also check `copy_state` and `empty_state` — if `copy_state` copies field by field, add the new one.

- [ ] **Step 5: Run tests**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 6: Format and commit**

```bash
git add src/ebpy/models.py src/ebpy/store/state.py tests/test_state.py && git commit -m "feat(store): record the packages the contract does not cover"
```

---

## Task 17: A package leaving the ceiling's coverage fails closed

**Files:**
- Create: `src/ebpy/decide/unmeasured.py`
- Modify: `src/ebpy/commands/check.py`, `src/ebpy/commands/prune.py`, `src/ebpy/commands/freeze.py`, `src/ebpy/commands/report.py`
- Modify: `src/ebpy/decide/analysis_report.py` (`AnalyzerSummary.unmeasured`, backlog carry)
- Modify: `src/ebpy/render/analysis_report.py` (the unmeasured line)
- Test: `tests/test_unmeasured.py`, `tests/test_check.py`, `tests/test_prune.py`, `tests/test_freeze.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `AnalysisMeasurement.unmeasured` (Task 7); `State.unmeasured_packages` (Task 16).
- Produces:
  - `UnmeasuredVerdict(scopes, packages, measured, regressed, lost_cells)`
  - `unmeasured_verdict(measurement, previous, baseline) -> UnmeasuredVerdict`
  - `next_unmeasured_packages(previous, verdict) -> tuple[str, ...]`
  - `unmeasured_notice(verdict) -> list[str]` (not a regression — informational)
  - `regression_refusal(verdict) -> str`

**The rule, in one line:**

```
regressed  =  clippy ∈ frozen_analyzers  AND  this run's packages ⊄ ledger's unmeasured_packages
```

**Every clause carries weight:**

- **`clippy ∈ frozen_analyzers` cannot be dropped.** Outside the contract clippy holds no ceiling, so claiming a regression would gate on a ceiling that does not exist — colliding head-on with `tests/test_check.py:134`'s `test_a_non_contract_analyzer_is_named_but_never_gates`. The realistic shape: no config, contract `{ruff, mypy}`, Rust and Python side by side, `fuzz` mismatched. Drop the clause and **a Python repository's `check` fails because of a Rust fuzz workspace.**
- **Subset, not equality.** Coverage *widening* (a previously dropped workspace becoming measurable) passes and updates the contract.
- **Cells never enter the judgment.** They cannot: zero-count cells are not written, so a clean workspace and an unmeasured one look identical. Cells are used only to *name* what is at stake — the display side may approximate; the judgment may not.
- **Set containment, not path prefixes.** That is what makes `[lib] path = "../shared/lib.rs"` and two workspaces compiling one `.rs` both come out right.

**Per command:**

| command | on regression | writes `unmeasured_packages`? |
| --- | --- | --- |
| `check` | refuse, naming the workspaces and the cells at stake | yes, when clippy measured completely and did not regress; otherwise **carry the previous value** |
| `prune` | refuse (it touches the ceiling) | same |
| `freeze` (non-`--force`) | refuse — though `_already_frozen` usually refuses first | same |
| `freeze --force` | proceed; this is the deliberate narrowing | rewrite from this run |
| `freeze --analyzer ruff`/`mypy` | n/a | **untouched** — this run did not measure clippy |
| `report` | never refuses; renders the notice and **carries the baseline backlog** | never writes |

- **`check --write` must write this key.** `check` already persists state (`commands/check.py:188`), including after a failure (`tests/test_check.py:449`). If only `freeze`/`prune` wrote it: freeze with `{fuzz}` dropped → fix the `cfg` → `check` measures everything → the ledger still says `{fuzz}` → break it again → `{fuzz} ⊆ {fuzz}` passes, and **a range that was measured once silently disappears the second time.**
- **"Persist `decision.state`" and "replace this key" are different events.** The first happens even when the gate fails; the second happens only when clippy measured completely and passed containment. Overwriting the contract with an empty set from a run that never happened records "nothing is excluded" as the outcome of not looking.
- **`report`'s backlog must be carried, not pruned.** `_backlog_cells_for` prunes the baseline against the current measurement when the status is `complete`. Under a regression, the dropped workspace's cells are absent from the measurement, so the prune erases them from the displayed backlog — it looks fixed. Route it down the same path as a failed or incomplete run.
- **The status stays `complete`.** `unattributed` is empty, so `classify` says `complete`, and it is right: what was measured, was measured. Whether that narrows the contract is the ceiling-aware layer's call. Forcing `incomplete` would permanently refuse every repository with a legitimately unmeasurable workspace (tokio's shape).
- **`store/baseline.py` and `prune_cells` do not change.** Under a regression `prune` never runs; without one there is no ceiling to protect. No carry-forward machinery is needed.
- **Nothing is added to `diagnose`.** It is a pure function over `RepoFacts` and never measures; producing this would require launching cargo from the wrong layer. Feeding it the ledger's stored set instead would report the last freeze's facts as though they were today's.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_unmeasured.py`:

```python
"""Whether this run's unmeasured packages narrow the frozen contract."""

from __future__ import annotations

from ebpy.decide.unmeasured import next_unmeasured_packages, unmeasured_verdict
from ebpy.measurement import Failed, Measured, Measurement
from ebpy.models import AnalysisMeasurement, State, UnmeasuredScope


def _measurement(*scopes: UnmeasuredScope) -> Measurement:
    return Measurement(
        {"clippy": Measured(tool="clippy", value=AnalysisMeasurement(cells={}, unmeasured=scopes))}
    )


def _scope(root: str, *packages: str) -> UnmeasuredScope:
    return UnmeasuredScope(root=root, packages=packages or (root,))


def test_a_range_that_was_never_covered_passes() -> None:
    """tokio's shape: a fuzz workspace that never compiled in this configuration."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    assert not unmeasured_verdict(_measurement(_scope("fuzz")), state, {}).regressed


def test_a_package_that_was_covered_and_is_no_longer_fails_closed() -> None:
    """The cells cannot answer this: a clean workspace writes none, exactly like an unmeasured one."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    verdict = unmeasured_verdict(_measurement(_scope(".", "fuzz", "core")), state, {})
    assert verdict.regressed


def test_a_workspace_root_staying_the_same_does_not_hide_a_moved_package() -> None:
    """`members` and `exclude` move packages across an unchanged root; roots cannot see that."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    verdict = unmeasured_verdict(_measurement(_scope(".", "fuzz", "core")), state, {})
    assert verdict.regressed
    assert verdict.scopes[0].root == "."


def test_coverage_widening_passes_and_updates_the_contract() -> None:
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    verdict = unmeasured_verdict(_measurement(), state, {})
    assert not verdict.regressed
    assert next_unmeasured_packages(state, verdict) == ()


def test_deleting_a_crate_is_never_a_regression() -> None:
    """Remembering the measured set instead would demand a --force for every deletion."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    assert not unmeasured_verdict(_measurement(_scope("fuzz")), state, {}).regressed


def test_a_repository_that_does_not_ratchet_clippy_never_regresses() -> None:
    """Otherwise a Python repository's check fails because of a Rust fuzz workspace."""
    state = State(frozen_analyzers=("ruff", "mypy"))
    assert not unmeasured_verdict(_measurement(_scope("fuzz")), state, {}).regressed


def test_a_failed_run_carries_the_previous_contract_rather_than_emptying_it() -> None:
    """A run that never happened must not record "nothing is excluded"."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    measurement = Measurement({"clippy": Failed(tool="clippy", failure_kind="execution-failed", detail="x")})
    verdict = unmeasured_verdict(measurement, state, {})
    assert not verdict.measured
    assert next_unmeasured_packages(state, verdict) == ("fuzz",)


def test_a_run_that_did_not_measure_clippy_at_all_carries_the_contract() -> None:
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=("fuzz",))
    verdict = unmeasured_verdict(Measurement({}), state, {})
    assert next_unmeasured_packages(state, verdict) == ("fuzz",)


def test_the_cells_at_stake_are_named_from_the_newly_dropped_packages() -> None:
    """Judgment is set containment; naming is an approximation, and that split is deliberate."""
    state = State(frozen_analyzers=("clippy",), unmeasured_packages=())
    baseline = {"core/src/lib.rs": {"clippy:clippy::x": 3}, "other/src/lib.rs": {"clippy:clippy::y": 1}}
    verdict = unmeasured_verdict(_measurement(_scope("core")), state, baseline)
    assert verdict.regressed
    assert any("core/src/lib.rs" in cell for cell in verdict.lost_cells)
```

Add to `tests/test_check.py`:

```python
def test_check_refuses_when_a_workspace_that_held_a_ceiling_stops_compiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Written with a fixture that has no cells at all: a cell-based rule would pass here."""
    _write_frozen_pair(tmp_path, frozen_analyzers=("clippy",), cells={})
    measurement = Measurement(
        {
            "clippy": Measured(
                tool="clippy",
                value=AnalysisMeasurement(
                    cells={}, unmeasured=(UnmeasuredScope(root=".", packages=("core",)),)
                ),
            )
        }
    )
    monkeypatch.setattr(check_command, "measure_repository", lambda _cwd, _scope: measurement)
    result = check_command.run_check(tmp_path, write=False)
    assert not result.ok
    assert "core" in result.message
    assert "freeze --force" in result.message


def test_check_records_a_widened_contract_so_a_second_break_is_still_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If only freeze and prune wrote the key, breaking it a second time would pass silently."""
    _write_frozen_pair(tmp_path, frozen_analyzers=("clippy",), cells={}, unmeasured_packages=("fuzz",))
    measurement = Measurement(
        {"clippy": Measured(tool="clippy", value=AnalysisMeasurement(cells={}))}
    )
    monkeypatch.setattr(check_command, "measure_repository", lambda _cwd, _scope: measurement)
    assert check_command.run_check(tmp_path, write=True).ok
    assert read_ledger(tmp_path).state.unmeasured_packages == ()


def test_a_failing_check_persists_state_without_emptying_the_unmeasured_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Persisting the state and replacing this key are different events."""
    _write_frozen_pair(tmp_path, frozen_analyzers=("clippy",), cells={}, unmeasured_packages=("fuzz",))
    measurement = Measurement(
        {"clippy": Failed(tool="clippy", failure_kind="execution-failed", detail="boom")}
    )
    monkeypatch.setattr(check_command, "measure_repository", lambda _cwd, _scope: measurement)
    assert not check_command.run_check(tmp_path, write=True).ok
    assert read_ledger(tmp_path).state.unmeasured_packages == ("fuzz",)
```

Plus, in the same style: `prune` refuses under the same condition; `freeze --force` proceeds and rewrites the key; `freeze --analyzer ruff` leaves it untouched; `report` does not refuse, shows the notice, and keeps the baseline backlog total.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_unmeasured.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ebpy.decide.unmeasured'`

- [ ] **Step 3: Write the decision module**

Create `src/ebpy/decide/unmeasured.py`:

```python
"""Whether the ranges this run could not measure narrow the frozen contract.

The runner reports one fact — "this range was not measured". Whether that fact is a
regression needs the ceiling, which the measurement seam deliberately does not know
(`docs/measurement-seam.md`: *The seam owns measured facts. It does not own ceilings, gate
policy or persistence.*). That judgment lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ebpy.measurement import Measured, classify
from ebpy.store.baseline import cells_for

if TYPE_CHECKING:
    from ebpy.measurement import Measurement
    from ebpy.models import CellCounts, State, UnmeasuredScope

_ANALYZER = "clippy"
_NAMED_CELLS = 5


@dataclass(frozen=True)
class UnmeasuredVerdict:
    """What this run did not measure, and whether that is a narrowing of the contract."""

    scopes: tuple[UnmeasuredScope, ...]
    packages: tuple[str, ...]
    # Whether clippy produced a complete measurement this run. Only then may the contract's
    # recorded set be replaced — an empty set from a run that never happened would record
    # "nothing is excluded" as the outcome of not looking.
    measured: bool
    regressed: bool
    # Baseline cells inside the newly dropped packages, for the message. Approximate on
    # purpose: the judgment above is set containment and must be sound; naming may not be.
    lost_cells: tuple[str, ...]


def unmeasured_verdict(
    measurement: Measurement, previous: State, baseline: CellCounts
) -> UnmeasuredVerdict:
    """Decide whether this run's unmeasured ranges leave the contract's coverage."""
    observation = measurement.analyzers.get(_ANALYZER)
    measured = isinstance(observation, Measured) and classify(observation) == "complete"
    scopes = observation.value.unmeasured if isinstance(observation, Measured) else ()
    packages = tuple(sorted({package for scope in scopes for package in scope.packages}))
    covered = set(previous.unmeasured_packages)
    newly = sorted(set(packages) - covered)
    # Kept: outside the contract clippy holds no ceiling, and claiming a regression there
    # would gate on a ceiling that does not exist — which is the invariant
    # `test_a_non_contract_analyzer_is_named_but_never_gates` already pins. Without it, a
    # Python repository's check fails because of a Rust fuzz workspace sitting beside it.
    regressed = _ANALYZER in previous.frozen_analyzers and bool(newly)
    return UnmeasuredVerdict(
        scopes=scopes,
        packages=packages,
        measured=measured,
        regressed=regressed,
        lost_cells=_cells_under(baseline, newly) if regressed else (),
    )


def _cells_under(baseline: CellCounts, packages: list[str]) -> tuple[str, ...]:
    prefixes = tuple(f"{package}/" for package in packages if package != ".")
    named = [
        f"{file}:{rule}"
        for file, rules in sorted(cells_for(baseline, _ANALYZER).items())
        for rule in sorted(rules)
        if not prefixes or file.startswith(prefixes)
    ]
    return tuple(named[:_NAMED_CELLS])


def next_unmeasured_packages(previous: State, verdict: UnmeasuredVerdict) -> tuple[str, ...]:
    """The set to persist: this run's, but only from a run that actually measured and passed."""
    if verdict.measured and not verdict.regressed:
        return verdict.packages
    return previous.unmeasured_packages


def unmeasured_notice(verdict: UnmeasuredVerdict) -> list[str]:
    """Say out loud which ranges hold no ceiling, and what that costs.

    The last sentence is the point: a range ebpy never measured is not gated either. Its
    ceiling cannot fall, but it cannot rise, and a reader has to be able to find that out
    somewhere other than this file.
    """
    if not verdict.scopes:
        return []
    count = len(verdict.scopes)
    return [
        f"{count} workspace(s) not measured in this configuration:",
        *(
            f"  {scope.root} does not compile in the configuration ebpy measures."
            " It references items hidden behind a `cfg`. ebpy holds no ceiling for it,"
            " and new violations there are not gated."
            for scope in verdict.scopes
        ),
    ]


def regression_refusal(verdict: UnmeasuredVerdict) -> str:
    """Name what stopped being measured, and offer both exits rather than choosing one."""
    return "\n".join(
        [
            *(
                f"{scope.root} no longer compiles in the configuration ebpy measures."
                for scope in verdict.scopes
            ),
            *(f"  {cell}" for cell in verdict.lost_cells),
            "Fix the `cfg` so these compile again, or run `ebpy freeze --force`",
            "to accept the narrower contract deliberately.",
        ]
    )
```

- [ ] **Step 4: Wire `check`**

In `src/ebpy/commands/check.py`, after computing the measurement:

```python
    measurement = measure_repository(cwd, scope.to_measure)
    verdict = unmeasured_verdict(measurement, previous, artifacts.cells)
    decision = check_measurement(previous, artifacts.cells, measurement)
    # Persisting the state and replacing this key are different events: state is written even
    # after a failing gate, but the contract's coverage is only rewritten by a run that
    # actually measured clippy and stayed inside it.
    decision.state.unmeasured_packages = next_unmeasured_packages(previous, verdict)
    if verdict.regressed:
        result = CheckResult(ok=False, message=regression_refusal(verdict))
    else:
        notice = unmeasured_notice(verdict)
        message = "\n\n".join([decision.result.message, *(["\n".join(notice)] if notice else [])])
        result = CheckResult(ok=decision.result.ok, message=message)
    if write:
        write_state(cwd, decision.state)
        write_quality_file(cwd, decision.state)
    return result
```

- [ ] **Step 5: Wire `prune`, `freeze` and `report`**

`prune`: after measuring, `verdict = unmeasured_verdict(measurement, previous, artifacts.cells)`; `raise CommandError(regression_refusal(verdict))` when `verdict.regressed`; otherwise set `decision.state.unmeasured_packages = next_unmeasured_packages(previous, verdict)` and append `unmeasured_notice(verdict)` to the message.

`freeze`: after measuring, compute the verdict against `previous`. When `analyzer is None or analyzer == "clippy"`, set `decision.state.unmeasured_packages = verdict.packages if verdict.measured else previous.unmeasured_packages`. `--force` proceeds regardless — that is the deliberate narrowing — while a non-force global freeze on a frozen contract never gets here (`_already_frozen` refuses first). A `freeze --analyzer ruff` never touches the key, which falls out of the branch above because clippy is not in that run's scope. Append `unmeasured_notice(verdict)` to the message.

`report`: compute the verdict, pass `frozenset({"clippy"}) if verdict.regressed else frozenset()` as a new `carry_backlog` argument to `report_from_measurement`, and let the summary carry the scopes.

- [ ] **Step 6: Carry the backlog and surface the scopes in `report`**

In `src/ebpy/decide/analysis_report.py`, add `unmeasured: tuple[UnmeasuredScope, ...]` to `AnalyzerSummary` (read from the `Measured` value in `_analyzer_summary`, `()` otherwise), serialize it in `to_dict` as `"unmeasured": [{"root": s.root, "packages": list(s.packages)} for s in summary.unmeasured]`, and add the carry parameter:

```python
def _backlog_cells_for(
    analyzer: str, baseline: CellCounts, measurement: Measurement, carry: bool
) -> CellCounts:
    """Backlog cells for one contract analyzer.

    `carry` forces the fallback even for a complete observation. Under a coverage regression
    the dropped workspace's cells are simply absent from this run, so pruning against it
    would erase them from the displayed backlog — the debt would look fixed. `report` writes
    nothing, but a backlog that falls only on screen is as misleading as one that falls.
    """
    observation = measurement.analyzers.get(analyzer)
    if not carry and isinstance(observation, Measured) and classify(observation) == "complete":
        return prune_cells(cells_for(baseline, analyzer), cells_for(observation.value.cells, analyzer))
    return cells_for(baseline, analyzer)
```

with `carry_backlog: frozenset[str] = frozenset()` on `report_from_measurement` and `analyzer in carry_backlog` passed through.

In `src/ebpy/render/analysis_report.py`, render `summary.unmeasured` as a line under the analyzer table for any summary that carries one.

- [ ] **Step 7: Run tests**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 8: Format and commit**

```bash
git add src/ebpy/decide/ src/ebpy/render/analysis_report.py src/ebpy/commands/ tests/ && git commit -m "feat(ratchet): fail closed when a package leaves the ceiling's coverage"
```

---

**Stage #3 of the spec (§7) is complete.**

---

## Task 18: Python-only subcommands refuse a repository with no Python

**Files:**
- Modify: `src/ebpy/commands/diagnose.py`, `src/ebpy/commands/bootstrap.py`, `src/ebpy/commands/catalog.py`, `src/ebpy/commands/next_command.py`
- Test: `tests/test_diagnose.py`, `tests/test_bootstrap.py`, `tests/test_catalog.py`, `tests/test_worklist.py` (or wherever `run_next` is exercised)

**Interfaces:**
- Consumes: `has_python`, `languages_from_files` (Task 2).

**What each of them renders today in a Rust-only repository, with no error:**

| code | output |
| --- | --- |
| `repo/facts.py:84,131` (hard-coded `.py`) | `SizeDistribution(total=0)` — reads as "0 files over 600 lines" |
| `repo/detect/package_manager.py:33` | default `"pip"` — a cargo project displayed as pip |
| `catalog.py:111-118` | `"No public functions found."` |
| `repo/fan_in.py` | `--fan-in`'s importers quietly empty |

All four report "nobody looked" as "zero".

**Where each guard's answer comes from:**

| command | source |
| --- | --- |
| `diagnose`, `bootstrap` | `languages_from_files(facts.all_files)` — both already called `gather_facts` |
| `catalog`, `next --fan-in` | `has_python(cwd)` — neither builds `RepoFacts` |

`diagnose` and `bootstrap` must **not** call `has_python(cwd)`: it would walk the same tree a second time, against `RepoFacts`'s "read once" contract, and Task 14 already computes `languages` there for the detector filter — the same value serves both.

`install` and `skills install` are unchanged: they already refuse without `pyproject.toml` (`install.py:165`, `skills_install.py:292`).

`next` without `--fan-in` stays supported: it ranks from ceiling cells alone (`next_command.py:31-38`).

- [ ] **Step 1: Write the failing tests**

```python
def test_diagnose_refuses_a_repository_with_no_python(tmp_path: Path) -> None:
    """Its size distribution counts only .py, so it would report "0 files over 600 lines"."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    with pytest.raises(CommandError) as caught:
        run_diagnose(tmp_path, as_json=False, write=False)
    assert "Python" in str(caught.value)


def test_bootstrap_refuses_a_repository_with_no_python(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    with pytest.raises(CommandError):
        run_bootstrap(tmp_path, dry_run=True, python_version="3.11")


def test_catalog_refuses_a_repository_with_no_python(tmp_path: Path) -> None:
    """It would write "No public functions found." over a repository full of Rust."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    with pytest.raises(CommandError):
        run_catalog(tmp_path)


def test_next_with_fan_in_refuses_a_repository_with_no_python(tmp_path: Path) -> None:
    """The importer graph resolves Python imports; without Python it is silently empty."""
    _write_frozen_pair(tmp_path, frozen_analyzers=("clippy",), cells={"src/lib.rs": {"clippy:x": 1}})
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    with pytest.raises(CommandError):
        run_next(tmp_path, as_json=False, fan_in=True)


def test_next_without_fan_in_still_works_on_a_rust_repository(tmp_path: Path) -> None:
    """It ranks from ceiling cells alone, which are language-independent."""
    _write_frozen_pair(tmp_path, frozen_analyzers=("clippy",), cells={"src/lib.rs": {"clippy:x": 1}})
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert run_next(tmp_path, as_json=False, fan_in=False)


def test_a_mixed_repository_still_runs_every_python_command(tmp_path: Path) -> None:
    """The refusal is for repositories with no Python, never for repositories that also have Rust."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\nname='a'\n", encoding="utf-8")
    assert run_diagnose(tmp_path, as_json=False, write=False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_diagnose.py tests/test_catalog.py -v`
Expected: FAIL — `DID NOT RAISE CommandError`

- [ ] **Step 3: Add a shared message**

In `src/ebpy/repo/detect/language.py`:

```python
def no_python_message(command: str) -> str:
    """Explain why a Python-only command will not run here.

    Refusing rather than returning empty results: every one of these reads `.py` files and
    would otherwise report "nobody looked" as "zero" — a cargo project shown as using pip,
    or "0 files over 600 lines" for a repository with no Python files to count.
    """
    return "\n".join(
        [
            f"`ebpy {command}` reads Python sources, and this repository has none.",
            "Its answer would be an empty result rather than a finding, so nothing was run.",
            "`ebpy freeze`, `check`, `prune`, `report`, `status`, `log`, `secrets` and `next`",
            "all work here.",
        ]
    )
```

- [ ] **Step 4: Guard the four commands**

`src/ebpy/commands/diagnose.py`, after `gather_facts`:

```python
    facts = gather_facts(cwd)
    languages = languages_from_files(facts.all_files)
    if "python" not in languages.languages:
        raise CommandError(no_python_message("diagnose"))
    diagnosis = diagnose(facts, frozen_analyzers, languages.languages)
```

`src/ebpy/commands/bootstrap.py`, the same shape with `no_python_message("bootstrap")`.

`src/ebpy/commands/catalog.py`, at the top of `run_catalog`:

```python
    if not has_python(cwd):
        raise CommandError(no_python_message("catalog"))
```

`src/ebpy/commands/next_command.py`, inside `run_next` before `_gather_importers`:

```python
    if fan_in and not has_python(cwd):
        raise CommandError(no_python_message("next --fan-in"))
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 6: Format and commit**

```bash
git add src/ebpy/repo/detect/language.py src/ebpy/commands/ tests/ && git commit -m "feat(commands): refuse Python-only subcommands where there is no Python"
```

---

**Stage #4 of the spec (§7) is complete.**

---

## Task 19: The lifecycle test that pins cargo's diagnostic re-emission

**Files:**
- Create: `tests/test_clippy_lifecycle.py`
- Test: itself

**Interfaces:**
- Consumes: everything. Drives `ebpy.cli.main` end to end.

**What this test actually contracts, and why the note in it matters more than the numbers.** ebpy depends on cargo re-emitting saved diagnostics for units it did not recompile — otherwise a second `ebpy check` would see fewer findings and the ratchet would report phantom progress. **This is observed only; no documentation was found for it**, and this area has a history of "no warnings on the second run" bugs. The private `--target-dir` does not help (the second run is still not recompiled), and `cargo clean` every time is not affordable. So it becomes an invariant CI holds.

Put this in the test file itself, because a future maintainer will meet a red test and reach for the fastest green:

> If a future cargo makes this fail, **do not adjust the expected value to the observed one.** What this test contracts is not the number; it is the premise that ebpy may rely on re-emission at all. A failure means the premise broke, so the measurement strategy has to be redesigned (measure cold every time, or stop depending on re-emission). Rewriting 4 to 2 breaks the ceiling silently.

**Skip on `cargo clippy --version` not succeeding — not on cargo being absent.** A minimal rustup profile ships cargo without the clippy component (reproduced on 1.70).

- [ ] **Step 1: Write the test file**

Create `tests/test_clippy_lifecycle.py`, modelled on `tests/test_mypy_lifecycle.py`:

```python
"""End-to-end lifecycle over a real Cargo repository.

The ratchet's "can fall, never rise" claim has to hold for clippy cells too. Each test builds
its own fixture and drives the CLI through one complete sub-arc. These are slow because they
compile Rust; keep every fixture to one tiny crate.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from ebpy.cli import main
from ebpy.store.state import read_ledger

if TYPE_CHECKING:
    from pathlib import Path


def _clippy_available() -> bool:
    """Skip on clippy, not on cargo: a minimal rustup profile has cargo and no clippy component."""
    if shutil.which("cargo") is None:
        return False
    probe = subprocess.run(["cargo", "clippy", "--version"], capture_output=True, text=True, check=False)
    return probe.returncode == 0 and probe.stdout.startswith("clippy ")


pytestmark = pytest.mark.skipif(
    not _clippy_available(), reason="needs a toolchain whose `cargo clippy --version` succeeds"
)

_MANIFEST = "[package]\nname = 'demo'\nversion = '0.1.0'\nedition = '2021'\n"

# `needless_return` is among clippy's oldest and most stable lints, so the expected counts
# depend on the code rather than on which toolchain happens to be installed.
_DIRTY = "pub fn a() -> i32 {\n    return 1;\n}\n\npub fn b() -> i32 {\n    return 2;\n}\n"
_CLEAN = "pub fn a() -> i32 {\n    1\n}\n\npub fn b() -> i32 {\n    2\n}\n"

_RULE = "clippy:clippy::needless_return"


def _crate(root: Path, body: str) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(_MANIFEST, encoding="utf-8")
    (root / "src" / "lib.rs").write_text(body, encoding="utf-8")


def _cells(root: Path) -> dict[str, dict[str, int]]:
    return json.loads((root / ".ebpy" / "baseline.json").read_text(encoding="utf-8"))["cells"]


def test_freeze_pins_todays_clippy_warnings_as_the_ceiling(tmp_path: Path) -> None:
    _crate(tmp_path, _DIRTY)
    assert main(["freeze", "--cwd", str(tmp_path)]) == 0
    assert _cells(tmp_path)["src/lib.rs"][_RULE] == 2
    assert read_ledger(tmp_path).state.frozen_analyzers == ("clippy",)


def test_check_passes_at_the_ceiling_and_fails_above_it(tmp_path: Path) -> None:
    _crate(tmp_path, _DIRTY)
    main(["freeze", "--cwd", str(tmp_path)])
    assert main(["check", "--cwd", str(tmp_path)]) == 0
    (tmp_path / "src" / "lib.rs").write_text(
        _DIRTY + "\npub fn c() -> i32 {\n    return 3;\n}\n", encoding="utf-8"
    )
    assert main(["check", "--cwd", str(tmp_path)]) != 0


def test_a_second_measurement_of_an_unchanged_repository_counts_the_same(tmp_path: Path) -> None:
    """cargo re-emits saved diagnostics for units it did not recompile.

    Observed only — no documentation was found for it, and this area historically carried
    "no warnings on the second run" bugs. Splitting the target directory does not help,
    because the second run is still not recompiled, and `cargo clean` every time is not
    affordable. So the premise becomes an invariant CI holds.

    If a future cargo makes this fail, DO NOT adjust the expected value to the observed one.
    What is contracted here is not the number 2; it is that ebpy may rely on re-emission at
    all. A failure means that premise broke and the measurement strategy has to change —
    measure cold every time, or stop depending on re-emission. Rewriting 2 to 0 would leave
    a ceiling that silently stops holding.
    """
    _crate(tmp_path, _DIRTY)
    main(["freeze", "--cwd", str(tmp_path)])
    first = _cells(tmp_path)["src/lib.rs"][_RULE]
    assert main(["freeze", "--force", "--cwd", str(tmp_path)]) == 0
    assert _cells(tmp_path)["src/lib.rs"][_RULE] == first


def test_prune_lowers_the_ceiling_after_a_fix_and_never_raises_it(tmp_path: Path) -> None:
    _crate(tmp_path, _DIRTY)
    main(["freeze", "--cwd", str(tmp_path)])
    (tmp_path / "src" / "lib.rs").write_text(_CLEAN, encoding="utf-8")
    assert main(["prune", "--cwd", str(tmp_path)]) == 0
    assert _cells(tmp_path) == {}
    (tmp_path / "src" / "lib.rs").write_text(_DIRTY, encoding="utf-8")
    assert main(["check", "--cwd", str(tmp_path)]) != 0


def test_a_rule_id_keeps_its_clippy_prefix_through_the_work_log(tmp_path: Path) -> None:
    """`split_rule` splits on the first colon only, so a local code may hold colons itself."""
    _crate(tmp_path, _DIRTY)
    main(["freeze", "--cwd", str(tmp_path)])
    assert main(["log", "drained", "fixed one", "--rule", _RULE, "--cwd", str(tmp_path)]) == 0


def test_a_mixed_repository_freezes_every_analyzer_together(tmp_path: Path) -> None:
    _crate(tmp_path, _DIRTY)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n", encoding="utf-8")
    (tmp_path / "mod.py").write_text("import os\n", encoding="utf-8")
    assert main(["freeze", "--cwd", str(tmp_path)]) == 0
    assert set(read_ledger(tmp_path).state.frozen_analyzers) == {"clippy", "mypy", "ruff"}
```

Check `ebpy.cli.main`'s actual argument shape before writing these — if there is no `--cwd` flag, use `monkeypatch.chdir(tmp_path)` and call `main(["freeze"])`. The mixed test also needs ruff and mypy present, so guard it with the same skip `tests/test_mypy_lifecycle.py` uses.

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_clippy_lifecycle.py -v`
Expected: PASS, or all-skipped where no clippy toolchain is installed. If they run, expect them to be slow (a first compile fetches nothing here, since the fixture has no dependencies).

- [ ] **Step 3: Format and commit**

```bash
git add tests/test_clippy_lifecycle.py && git commit -m "test(clippy): pin the full ratchet lifecycle over a real Cargo repository"
```

---

## Task 20: The documentation the change makes wrong

**Files:**
- Modify: `docs/measurement-seam.md`, `docs/cli/report.md`, the rest of `docs/cli/*.md`
- Modify: `CLAUDE.md`
- Modify: `README.md:5`, `pyproject.toml` (`description`), `src/ebpy/cli.py:1` and `:71`, `src/ebpy/__init__.py:1`
- Modify: `src/ebpy/commands/log.py` (`RULE_HINT`)
- Modify: `src/ebpy/generate/workflows.py` (`gate_workflow` docstring)
- Test: none new — this is prose. `uv run pytest` still has to pass, since some tests assert CLI help text.

**The complete list. Each item is wrong *after* this change, not merely improvable:**

1. **`docs/measurement-seam.md`, four places naming ruff and mypy as the whole set:** the `measure_repository(cwd)` signature; the structure diagram's `├── ruff` / `└── mypy`; *"Ruff and mypy are the two analyzers in the initial implementation."*; *"## Independent capabilities — Ruff and mypy are attempted independently."*
2. **`docs/measurement-seam.md`, "Command shape":** its ordering diagram has no scope step. Insert one.

   ```
   read and classify CeilingArtifacts
     -> preconditions
     -> [scope decision + reconciliation]
     -> measure_repository
     -> pure decisions
     -> persistence
   ```
3. **`docs/measurement-seam.md`, the `report --json` status list:** `no-runner` is **already** missing, and `scope-mismatch` is now missing too. Add both.
4. **`docs/measurement-seam.md`, "invalid always refuses before measuring":** global `freeze --force` is the exception. Not an exception this change creates — an existing recovery path the document never recorded.
5. **`docs/cli/report.md:95`:** the `--json` schema explains `unattributedTotal > 0` as an `incomplete`-only condition. After Task 6, `scope-mismatch` **and** unattributed co-occur. Rewrite each field in terms of **the observation behind it**, not of the status. Add the `unmeasured` field from Task 17.
6. **`CLAUDE.md` is stale independently of this work:** it says *the per-tool runners are `measurement/_ruff.py` and `measurement/_mypy.py`*. They are `tools/ruff/_runner.py` and `tools/mypy/_runner.py`; `measurement/` holds neither file. Fix it — the spec's own first draft was misled by this exact line. While there, add `tools/clippy/` and `repo/detect/language.py` to the shape-of-the-code section, and `decide/analyzer_scope.py` / `decide/unmeasured.py` to the `decide/` list.
7. **`tools/registry.py:61`'s comment** *"Order matches DETECTORS"* — corrected in Task 13; confirm it landed.
8. **`commands/log.py:24`'s `RULE_HINT`:** every example has exactly one colon, so `clippy:clippy::needless_return` looks malformed to a reader even though `is_rule_id` accepts it.

   ```python
   RULE_HINT = (
       "--rule must be a namespaced rule ID, e.g. ruff:C901, mypy:arg-type"
       " or clippy:clippy::needless_return"
   )
   ```
9. **`generate/workflows.py`'s `gate_workflow` docstring** says *"There is no raw `ruff check` or `mypy` step"*. The generated workflow itself does **not** change (Rust CI generation is out of scope), but the docstring's reasoning never depended on which analyzers exist. Restate it in the seam's words so it does not go stale each time the registry grows.
10. **The four "Python codebase" strings.** ebpy now measures Rust, so these are false. Change only these four — widening further is scope creep:

    | file | current |
    | --- | --- |
    | `src/ebpy/cli.py:1` and `:71` | *make a Python codebase that can only get better* |
    | `src/ebpy/__init__.py:1` | same |
    | `pyproject.toml` `description` | *Make an existing Python codebase one that can only get better* |
    | `README.md:5` | same |

    Replace "Python codebase" with "codebase". Keep *"a Python port of ever-better"* in the description — that describes ebpy's implementation language, which is still true.
11. **`docs/cli/freeze.md` / `check.md` / `prune.md` / `report.md` / `diagnose.md` / `catalog.md` / `next.md`:** add the refusals this change introduces — the empty-scope and scope-mismatch refusals, the Python-only guards, and the unmeasured-package regression.

- [ ] **Step 1: Fix the source strings and the hint**

Apply items 8, 9 and 10.

- [ ] **Step 2: Run tests**

Run: `uv run pytest -v`
Expected: PASS. If a test asserts the CLI banner text verbatim, update it.

- [ ] **Step 3: Commit the source-visible half**

```bash
git add src/ebpy/cli.py src/ebpy/__init__.py src/ebpy/commands/log.py src/ebpy/generate/workflows.py pyproject.toml README.md tests/ && git commit -m "docs: stop describing ebpy as measuring only Python"
```

- [ ] **Step 4: Rewrite `docs/measurement-seam.md`**

Apply items 1–4.

- [ ] **Step 5: Rewrite `docs/cli/*.md` and `CLAUDE.md`**

Apply items 5, 6 and 11.

- [ ] **Step 6: Verify the repository still gates itself**

Run: `uv run ruff format . && uv run pytest && uv run ebpy check`
Expected: PASS

- [ ] **Step 7: Commit the documentation**

```bash
git add docs/measurement-seam.md docs/cli/ CLAUDE.md && git commit -m "docs: describe the analyzer scope, clippy, and the statuses report can hold"
```

**Do not `git add docs/clippy-analyzer-spec.md` or `docs/superpowers/` here.** Both are already committed on this branch, and re-adding them would put an unrelated design document into a documentation commit.

---

## Task 21: The CI matrix that makes the supported Rust range real

**Files:**
- Modify: `.github/workflows/quality.yml`
- Test: CI itself — there is no unit test for a workflow file.

**Why this task exists.** §5.3 does not merely note that Rust versions differ; it *defines* a supported range (floor **1.79**, ceiling **current stable**) and names the CI matrix as the two points that make the range a claim rather than a hope. Every "根拠: 観測" line in the spec — the `--all-targets` double-count, `aborting due to N previous errors` having empty spans, the `configured out` note's wording, broken-manifest exit 101 — was measured across versions precisely so CI could keep re-measuring it. Without this task the integration tests from Tasks 7, 10 and 19 run on exactly one toolchain, which §5.3 says is worth "no more than 'no counterexample has appeared'".

**What the existing workflow already looks like.** `quality.yml`'s `quality` job matrixes `os: [ubuntu-latest, macos-latest, windows-latest]` × `python-version: ["3.10" … "3.14"]` — fifteen legs, none of which installs Rust. Crossing Rust into that matrix would make thirty, and twenty-eight of them would compile Rust to learn nothing about Python. **Add a separate job instead.**

**The floor is a decision, not a constant.** §5.3 says so explicitly: raising it is allowed, and the price of raising it is re-running the §5.2 rows that cite measurement. Put that sentence in the workflow next to the pinned version, because the pin is where somebody will meet it.

- [ ] **Step 1: Add the job**

In `.github/workflows/quality.yml`, after the `quality` job:

```yaml
  clippy-analyzer:
    # The two ends of the supported Rust range (spec §5.3). The clippy integration tests read
    # cargo's JSON output and its diagnostic re-emission behaviour, both of which move between
    # toolchains — one version proves only that no counterexample turned up on that version.
    # Raising the 1.79 floor is an allowed decision; whoever raises it re-runs the measured
    # claims in the spec's §5.2 against the new floor first.
    strategy:
      fail-fast: false
      matrix:
        rust: ["1.79", "stable"]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - name: Install Rust ${{ matrix.rust }}
        run: rustup toolchain install ${{ matrix.rust }} --profile minimal --component clippy
          && rustup default ${{ matrix.rust }}
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          python-version: "3.12"
      - name: Install
        run: uv sync --group dev
      - name: Clippy analyzer tests
        # Named explicitly rather than `uv run pytest`: this job exists for the tests that need
        # a toolchain, and the rest of the suite is already covered fifteen times over above.
        run: uv run pytest tests/test_clippy_topology.py tests/test_clippy_runner.py tests/test_clippy_lifecycle.py tests/test_clippy_ci_guard.py -v
        env:
          EBPY_REQUIRE_CLIPPY: "1"
```

`--component clippy` is not optional decoration: a minimal profile ships cargo without clippy, and the skip guard in Task 19 would then quietly skip the whole job green. **A job that installs a toolchain and skips every test is worse than no job** — it reports a range it never checked.

- [ ] **Step 2: Prove the guard cannot silently skip**

A check that fails loudly when CI asked for clippy and did not get it. It cannot live in `tests/test_clippy_lifecycle.py`: Task 19 puts a module-level `pytestmark` there that skips on exactly the condition this test needs to *assert*, so it would skip itself. Create `tests/test_clippy_ci_guard.py`:

```python
"""The one clippy test that must not skip when CI said it installed a toolchain."""

from __future__ import annotations

import os

import pytest

from tests.test_clippy_lifecycle import _clippy_available


def test_the_clippy_suite_is_not_silently_skipped_in_ci() -> None:
    """A green job that skipped every test would report a Rust range CI never exercised."""
    if os.environ.get("EBPY_REQUIRE_CLIPPY") != "1":
        pytest.skip("only enforced where CI installed a toolchain on purpose")
    assert _clippy_available(), "CI installed a toolchain but `cargo clippy --version` did not succeed"
```

Set `EBPY_REQUIRE_CLIPPY: "1"` in the job's `env:`, and add this file to the job's pytest arguments. The variable is the job saying *I installed clippy on purpose*; without it a developer's laptop still skips normally. If importing from a sibling test module is awkward under this repository's pytest layout, lift `_clippy_available` into `tests/conftest.py` and import it from there in both files.

- [ ] **Step 3: Verify the workflow parses**

Run: `uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/quality.yml'))"` if PyYAML is importable in the dev environment; it is not a dependency, so if it is not there, read the new job against the `quality` job above it and confirm the indentation matches. Either way the real verification is the first push — a malformed workflow does not run at all, which is the one failure mode that looks like silence rather than red.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/quality.yml tests/test_clippy_ci_guard.py && git commit -m "ci: run the clippy analyzer tests at both ends of the supported Rust range"
```

---

**Stage #5 of the spec (§7) is complete, and so is the plan.**

---

## Self-Review

Run against the spec after finishing, before declaring done.

**Spec coverage.** Every decision maps to a task:

| spec | task |
| --- | --- |
| D-1 scoped measurement | 4, 5 |
| D-2 `Analyzer.language` | 1 |
| D-3 language detection / `rust_topology` | 2, 7 |
| D-4 `ScopeDecision` | 3, 4, 5 |
| D-5 probe and measurement command | 10 |
| D-6 completeness, aggregation, configuration mismatch | 9, 10, 17 |
| D-7 cell conditions | 9 |
| D-8 rule ID spelling | 9, 20 |
| D-9 path handling | 8 |
| D-10 cached-diagnostic regression test | 19 |
| D-11 Python-only guards | 18 |
| D-12 no provisioner + freeze's `Unavailable` wording | 11 |
| D-13 detector language filter | 14 |
| D-14 `scope-mismatch` | 6 |
| D-15 `ClippyDetector` + facts | 12, 13 |
| D-16 unratcheted gap condition | 15 |
| D-17 `unmeasuredPackages` | 16, 17 |
| §2.1 subcommand support matrix | 4, 5, 18 |
| §2.5 the three failures guarded | 7, 9, 10, 17 |
| §5.3 support range at both ends | 7, 10, 19 (the tests); 21 (the matrix that runs them twice) |
| §7 documentation list | 20 |

**The gap this plan first left open, now closed:** §5.3's **CI matrix pinning Rust 1.79 and current stable** had no task, because `.github/workflows/quality.yml` had not been read when the plan was first written. It has been now, and Task 21 adds the matrix as a separate job rather than a fourth axis on the existing fifteen-leg Python matrix. Without it, every claim in the spec marked "観測" would be pinned at exactly one version — which §5.1 documents as the mistake that produced five falsified hypotheses.

**Placeholder scan.** No step says "add error handling", "handle edge cases", or "similar to Task N". Every code step carries the code. Three places name a value to be confirmed against the repository rather than guessed: `_write_frozen_pair`'s real helper name in `tests/test_check.py`, `render_quality_file`'s actual export name in `render/quality.py`, and `cli.main`'s argument shape in Task 19. Each says so explicitly at the point of use.

**Type consistency.** Names used across tasks, fixed once:

- `measure_repository(cwd, scope)` — `scope: tuple[str, ...]` in Tasks 4, 5, 11
- `ScopeDecision.to_measure` / `.global_freeze_scope` (tuples) and `.scope_mismatches` (frozenset) — Tasks 3–6
- `RepoLanguages.languages: frozenset[Language]` — the `.languages` attribute, not the value itself, is what `scope_decision` and `diagnose` receive (Tasks 3, 14, 15, 18)
- `UnmeasuredScope(root: str, packages: tuple[str, ...])` — Tasks 7, 9, 16, 17
- `AnalysisMeasurement(cells, unattributed, unmeasured)` — Tasks 7, 9, 10
- `PathVerdict(kind, path)` — Tasks 8, 9
- `RustWorkspace(root: PurePosixPath, target_directory: Path, packages: tuple[str, ...])` — Tasks 7, 9, 10
- `parse_clippy_output(stdout, stderr, returncode, *, workspace, repo_root)` — Tasks 9, 10
- `report_from_measurement(baseline, frozen_analyzers, measurement, scope_mismatches, carry_backlog)` — Tasks 6, 17. **Task 5 lands the three-argument form and Task 6 adds the fourth; Task 17 adds the fifth.** Both later arguments default, so no call site breaks in between.
- The repository root is spelled `"."` in both `UnmeasuredScope.packages` and `RustWorkspace.root` (Task 7, step 5's note) — the contract compares these sets directly, so one spelling is mandatory.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-28-clippy-analyzer.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — tasks executed in this session using executing-plans, batched with checkpoints for review.

Which approach?
