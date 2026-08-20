# CHANGELOG

<!-- version list -->

## Unreleased

### Breaking Changes

- Baseline and state files are now **version 2**. Rule IDs are namespaced: `ruff:F401`,
  `mypy:arg-type`. Version 1 artifacts are no longer read: a version-1 repository is named as an old
  format rather than corruption, and its contract must be re-pinned with `ebpy freeze --force`.
  Re-pinning discards more than the ceiling — the work log, the last diagnosis and the commit it was
  taken at are lost as well, since a forced freeze starts from an empty state.

- mypy is now gated per file per rule, not as a global total. A type error moving from one file to
  another fails `check` even when the repository-wide count is unchanged.

- Every freeze requires its in-scope analyzers to be measured completely. `freeze` and
  `freeze --force` alike refuse when any analyzer is unavailable, failed, or reported findings it
  could not attribute to a rule. `--force` now means only "re-pin over an existing or unreadable
  contract"; it does not exclude an incomplete analyzer.

- **No invocation removes an analyzer from a contract**, and the first contract always covers every
  analyzer. A repository whose toolchain is incomplete finishes `ebpy bootstrap` first.

- New `freeze --analyzer NAME` adds one analyzer to a contract whose roster is narrower than what
  ebpy knows — a contract pinned while an analyzer could not be measured. It adds that analyzer
  without disturbing the other ceilings.

- `report --json` schema replaced: `mypyErrors`, the global `filesWithFindings` scalar,
  `lintFailure`, and `mypyFailure` are gone, replaced by an `analyzers` object with per-analyzer
  `inContract`, `status`, `findings`, `filesWithFindings`, `failure`, `unattributedTotal`, and
  `unattributed` fields.

- `status --json` gains `frozenAnalyzers` and loses `counters`. `QUALITY.md` loses the
  `## Other counters` table and the regression verdict; it now lists analyzers by name.

- `check` now names the file of every finding beyond the ceiling, not just the rule.

## v0.3.2 (2026-08-19)

### Bug Fixes

- **freeze**: Normalize measurement failure detail
  ([`d316eb0`](https://github.com/yoshum/ebpy/commit/d316eb01e1ee44dabc681a85b1a75a05d1d9776d))

- **measurement**: Close the gaps the seam left open
  ([`a545ae6`](https://github.com/yoshum/ebpy/commit/a545ae618fde07861fbacceb21c950fde54606f8))

- **measurement**: Enforce failure and immutability contracts
  ([`4785c46`](https://github.com/yoshum/ebpy/commit/4785c462318200d8a80cc3440de100a2c243e89e))

- **measurement**: Keep a failure's detail, and choose its summary per tool
  ([`33f157b`](https://github.com/yoshum/ebpy/commit/33f157b0379702af7096fe8550bffa859ce37ba8))

### Code Style

- Format measurement changes
  ([`bed5369`](https://github.com/yoshum/ebpy/commit/bed536979f31e969e5505ce67da9d143b6dc81aa))

### Refactoring

- **check**: Decide from measurement values
  ([`7d9122f`](https://github.com/yoshum/ebpy/commit/7d9122fdbb4f4eb1d2ee6501d3541940ba363c0d))

- **freeze**: Build ceiling from measurement
  ([`fd95b98`](https://github.com/yoshum/ebpy/commit/fd95b989b046fe1ba1ce2ed45ffac0d77b4a33be))

- **measurement**: Add repository measurement seam
  ([`3a7724f`](https://github.com/yoshum/ebpy/commit/3a7724f5d7ba9481eee6c5d66963c823d9505fd4))

- **measurement**: Close direct runner interfaces
  ([`2e7ba50`](https://github.com/yoshum/ebpy/commit/2e7ba509d4b6f08cc549e896a4171304125237cf))

- **prune**: Lower ceiling from measurement
  ([`dd21b7c`](https://github.com/yoshum/ebpy/commit/dd21b7c89e634748d301824086d5460ce81d5fc1))

- **report**: Consume repository measurement
  ([`c348e72`](https://github.com/yoshum/ebpy/commit/c348e72a6765ad2dd902d5d5d66ddb0875ca4005))


## v0.3.1 (2026-08-18)

### Bug Fixes

- **ceiling**: Fail closed on invalid artifact pairs
  ([`fe71555`](https://github.com/yoshum/ebpy/commit/fe71555cd35e59cb8aaada3561994a9b5ae02661))

- **ceiling**: Reject artifact symlinks
  ([`6772094`](https://github.com/yoshum/ebpy/commit/677209447cddd121797fec8b4011a2ae65e1f09a))

### Refactoring

- **ceiling**: Simplify artifact handling
  ([`ec45111`](https://github.com/yoshum/ebpy/commit/ec45111bef5f68413ccdc1af7173b263befc035b))


## v0.3.0 (2026-08-18)

### Bug Fixes

- **install**: Address setup review findings
  ([`8eb8b2d`](https://github.com/yoshum/ebpy/commit/8eb8b2d21b8669a33894cbe5ba3c9811d5fff1cb))

- **install**: Harden skill setup edge cases
  ([`8240026`](https://github.com/yoshum/ebpy/commit/8240026e07d527cdec431675d6fcaeb265d1adcf))

- **install**: Reject bare pip fallback
  ([`fa3d8ac`](https://github.com/yoshum/ebpy/commit/fa3d8ac754402f670ebdeafa49da2f42e24631bc))

- **skills**: Remove obsolete managed roots
  ([`80ac310`](https://github.com/yoshum/ebpy/commit/80ac310433d8635cbc99500b1856d85a6837c84e))

- **skills**: Restore managed bundle after write failures
  ([`e872f87`](https://github.com/yoshum/ebpy/commit/e872f87b082e64267f5c125c4f10a9659a92ad86))

### Documentation

- **install**: Record why pip has no run prefix
  ([`ae50e55`](https://github.com/yoshum/ebpy/commit/ae50e555ff09e1ae8e43504035f418c0fb0c0d00))

### Features

- **install**: Add delegated project setup
  ([`b57101a`](https://github.com/yoshum/ebpy/commit/b57101a27c5b2e58451b280f80c6bbd965fd55f3))

### Refactoring

- **install**: Read the skills manifest once
  ([`4a0f7a7`](https://github.com/yoshum/ebpy/commit/4a0f7a773b9b69ef70c251e7e3614e43c09e2a30))


## v0.2.0 (2026-08-18)

### Features

- **skills**: Report at the freeze, where stopping is free
  ([`80abb7b`](https://github.com/yoshum/ebpy/commit/80abb7bb5125b8a0ba8c36cf212c501a1c057c61))


### Bug Fixes

- **skills**: Refuse to start on a dirty working tree
  ([`4bcafa7`](https://github.com/yoshum/ebpy/commit/4bcafa7bc10aeb93a26783be6d71ba7db223db6e))

- **skills**: Stop after two drain PRs fail CI in a row
  ([`59f5ba5`](https://github.com/yoshum/ebpy/commit/59f5ba5f60f8a82af1fb2169636e720c35061976))

- **skills**: Call ebpy from a released tag, not from a package index
  ([`f87572b`](https://github.com/yoshum/ebpy/commit/f87572b138b2ad01235ed92f5e710fe784ebe0d6))

- **skills**: Centralize ebpy command resolution
  ([`b84df23`](https://github.com/yoshum/ebpy/commit/b84df233a999cd3e5984c9e4f685e77b6d2a407c))


## v0.1.0 (2026-08-18)

- Initial Release
