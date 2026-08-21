# CHANGELOG

<!-- version list -->

## v0.5.3 (2026-08-21)

### Bug Fixes

- Report analyzer count in the global freeze message ([#24](https://github.com/yoshum/ebpy/pull/24),
  [`9b67d96`](https://github.com/yoshum/ebpy/commit/9b67d96b1f853917951830c2dece847057afbc56))


## v0.5.2 (2026-08-21)

### Bug Fixes

- Measure mypy exit-2 syntax errors instead of misreporting them
  ([#22](https://github.com/yoshum/ebpy/pull/22),
  [`92cff50`](https://github.com/yoshum/ebpy/commit/92cff50110e97b75d9acdb3d0f708c6b4e673a69))


## v0.5.1 (2026-08-21)

### Bug Fixes

- Defer to mypy config's own file selection instead of overriding with '.'
  ([#21](https://github.com/yoshum/ebpy/pull/21),
  [`bc5dfa1`](https://github.com/yoshum/ebpy/commit/bc5dfa1f0309c68aeb2a87c51583ddc4e259ad6a))

- Refuse foreign-flavour absolute mypy paths on any host
  ([`75dd3c9`](https://github.com/yoshum/ebpy/commit/75dd3c99c78ccccce2822f2a8e6a1928fecbd498))


## v0.5.0 (2026-08-21)

### Features

- Allow a scoped freeze to build a narrow contract on a fresh pair
  ([#20](https://github.com/yoshum/ebpy/pull/20),
  [`c713975`](https://github.com/yoshum/ebpy/commit/c71397554b8dc9988a4539a786291f6fb35d3085))

### Refactoring

- Rename misleading test helper and trim what-comment
  ([#17](https://github.com/yoshum/ebpy/pull/17),
  [`3e2e489`](https://github.com/yoshum/ebpy/commit/3e2e4892ef7ccb601d272303388e1e48dd7ecfca))


## v0.4.4 (2026-08-21)

### Bug Fixes

- Report consistent grandfathered total on prune no-op branches
  ([#16](https://github.com/yoshum/ebpy/pull/16),
  [`fdece5e`](https://github.com/yoshum/ebpy/commit/fdece5e912dd4c955b5ad50ebdb05f2c01686a33))


## v0.4.3 (2026-08-21)

### Bug Fixes

- Scoped forced freeze reports a replacement as a replacement
  ([#15](https://github.com/yoshum/ebpy/pull/15),
  [`2979ff3`](https://github.com/yoshum/ebpy/commit/2979ff3290af233b9a84d6d7707d8731e667e94b))


## v0.4.2 (2026-08-21)

### Bug Fixes

- Collapse duplicate non-contract analyzer notes in check
  ([#14](https://github.com/yoshum/ebpy/pull/14),
  [`3dade57`](https://github.com/yoshum/ebpy/commit/3dade575fe75442b90a94628463e4b23ca4f7d35))


## v0.4.1 (2026-08-21)

### Bug Fixes

- Surface mypy exit-1 errors that carry no location ([#13](https://github.com/yoshum/ebpy/pull/13),
  [`d6e1919`](https://github.com/yoshum/ebpy/commit/d6e191951b428a47f3203fb030af28ca7a5000eb))

### Refactoring

- Group the .ebpy/ ratchet files under store/
  ([`2322cb2`](https://github.com/yoshum/ebpy/commit/2322cb227c19a673aebd1721e682d0e86bb560b6))

- Group the pure verdict functions under decide/
  ([`6accff8`](https://github.com/yoshum/ebpy/commit/6accff844a449a28f9ae7dc3ea582abe6c6674df))

- Group the repository-reading modules under repo/
  ([`dbd1f57`](https://github.com/yoshum/ebpy/commit/dbd1f5742aa58553fd5f15870b334e0022d85b8d))

- Make measurement/ a package with private tool runners
  ([`ae2af6f`](https://github.com/yoshum/ebpy/commit/ae2af6fd0084ead0088c61fa96c71c21e337058b))


## v0.4.0 (2026-08-20)

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

### Bug Fixes

- **artifacts**: Name a version-1 repository as an old format, not corruption
  ([`682d7e2`](https://github.com/yoshum/ebpy/commit/682d7e245496fd78256778c8cb03056be2c10d91))

- **cell_key**: Reject a malformed v1 rule key instead of forging an id
  ([`425e667`](https://github.com/yoshum/ebpy/commit/425e6675f782a8573821e224980d4be24ed8f376))

- **cell_key**: Relativize a host-absolute path on any OS
  ([`a8a64ae`](https://github.com/yoshum/ebpy/commit/a8a64aee29493e08d45d666ec0d017a9c04bcb98))

- **check**: Point excess recovery at a scoped re-freeze
  ([`f7dd93e`](https://github.com/yoshum/ebpy/commit/f7dd93e2d317d154bbd5405da67eccb0c37b7d36))

- **freeze**: Keep an unmeasurable rostered analyzer instead of dropping it
  ([`98630f9`](https://github.com/yoshum/ebpy/commit/98630f9d10f80454fcdd3725e13a1dec6e77174d))

- **freeze**: Stop telling a mypy syntax error to edit Ruff config
  ([`14a22f4`](https://github.com/yoshum/ebpy/commit/14a22f4639b75c08e27b94c95f81700c37dc8a00))

- **mypy**: Stop a note line spelling an error from refusing the run
  ([`e6dbd64`](https://github.com/yoshum/ebpy/commit/e6dbd64ec5116e2a69ee394e7b60a588baf9c06e))

- **prune**: Drop a fully-fixed rule from the ledger, not just the baseline
  ([`a39880f`](https://github.com/yoshum/ebpy/commit/a39880f52676f0a72758778fcbcf50139d701e0f))

- **report**: Name the unparsed files of an incomplete analyzer
  ([`5f37237`](https://github.com/yoshum/ebpy/commit/5f37237e83e64a23090c18f45e7932837e27bcdb))

- **report**: Show an out-of-contract analyzer's failure reason in Markdown
  ([`26f2426`](https://github.com/yoshum/ebpy/commit/26f2426f0362581a84093b068530ca8b92d575df))

### Documentation

- Describe analyzers, namespaced rules and the v2 artifacts
  ([`589aeb0`](https://github.com/yoshum/ebpy/commit/589aeb07b5cc66d7a396f1277e791edc1d2d107e))

- **model**: Describe mypy as per-cell ratcheting, not a global counter
  ([`e20167e`](https://github.com/yoshum/ebpy/commit/e20167ee6cd89b48f896ee0cd13c534db53755b9))

### Features

- **analyzers**: Model mypy as namespaced analyzer cells
  ([`8f06ebd`](https://github.com/yoshum/ebpy/commit/8f06ebdc793b12c08a605cc140964d7122d2c2e4))

- **cells**: Add rule-ID namespace and analyzer path helpers
  ([`e12753b`](https://github.com/yoshum/ebpy/commit/e12753ba1517bead3f8b0376f2a40d3a9a9cb589))

- **mypy**: Parse mypy text output into namespaced cells
  ([`f4ccc29`](https://github.com/yoshum/ebpy/commit/f4ccc29a1a91920b21dfc15f7ddda04a9a6a0241))

### Refactoring

- **freeze**: Use analyzer_of to strip a scoped namespace
  ([`ac09b89`](https://github.com/yoshum/ebpy/commit/ac09b891c9e41d5867bc5e3c009912a59325dff1))

- **models**: Rename LintMeasurement to AnalysisMeasurement
  ([`7dfc090`](https://github.com/yoshum/ebpy/commit/7dfc09095afbb34a641e64dbc51dd31c32700286))

- **state**: Drop version-1 artifact reading
  ([`a1af0aa`](https://github.com/yoshum/ebpy/commit/a1af0aa93af223263634363bd7319858c8de9532))

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
