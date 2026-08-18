# CHANGELOG

<!-- version list -->

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
