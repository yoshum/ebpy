# Releasing

This repository ships from `main`. A merged pull request that changed what a tag delivers is a
release: the version moves, `CHANGELOG.md` gains a section, the commit is tagged, and GitHub gets a
Release. Nothing is uploaded to PyPI — the tag is the whole delivery, and
[the README](../README.md#install) installs from one.

The work is done by [python-semantic-release](https://python-semantic-release.readthedocs.io)
(the `release` dependency group), configured under `[tool.semantic_release]` in `pyproject.toml`.
`.github/workflows/release.yml` only decides *when* to call it.

## What decides a release

**Is there anything to release?** `commit_parser_options.path_filters` lists the release surface:

| Path | Why |
| --- | --- |
| `src/ebpy` | the command a tag delivers |
| `skills` | the skills a tag delivers |

A commit touching neither is ignored entirely — it moves no version and it appears in no changelog.
Changes to `tests/`, `docs/`, `.github/` or the README release nothing on their own, and are shipped
by whichever release comes next.

**How far does the version move?** From the Conventional Commits subjects of the commits that
survived that filter:

| In the range since the last tag | Bump |
| --- | --- |
| `feat!:`, or a `BREAKING CHANGE:` footer | major — but see below |
| `feat:` | minor |
| `fix:`, `perf:` | patch |
| `refactor:`, `chore:`, `style:`, `test:`, and subjects nobody wrote to the convention | none |

The last row means a refactor of shipped code does not release by itself. It sits on `main`,
untagged, until the next `feat:` or `fix:` takes it along — which is what a version number is for:
`0.4.1` should mean something changed for the caller.

Before 1.0.0 a breaking change moves the **minor** (`major_on_zero = false`): `0.x` promises
nothing, and reaching 1.0 should be a decision somebody made rather than one a `!` made for them.
Both zero-version knobs are set explicitly because python-semantic-release changed their defaults in
v10 — `allow_zero_version` is `false` there, which would take the next release to 1.0.0 on its own.

## What the run does

Triggered by `pull_request: [closed]` on `main`, and skipped unless the pull request merged.

1. Checks out `main` as a branch — not the merge commit. semantic-release refuses to release from a
   detached HEAD, and it verifies the upstream has not moved before it pushes.
2. Runs the whole gate: format, lint, mypy, pytest and `ebpy check --no-write`. `quality.yml` ran
   against each pull request's own head; two branches that are green apart can be broken together,
   and a tag is the wrong place to find that out.
3. `semantic-release version`, which stamps the version into `pyproject.toml`,
   `src/ebpy/__init__.py` and `uv.lock`, writes `CHANGELOG.md`, commits it as
   `chore(release): vX.Y.Z`, tags, pushes, and opens the GitHub Release. When the commits warrant no
   version it exits cleanly having done nothing.

`uv.lock` is stamped by `build_command`, which runs `uv lock --upgrade-package ebpy && git add
uv.lock`: the lockfile records the project's own version, so `uv sync --locked` starts failing the
moment `pyproject.toml` moves without it. `--upgrade-package` restamps that one entry and nothing
else — a release is the wrong moment to also take whatever landed upstream today. The two commands
are chained with `&&` deliberately: semantic-release reports a multi-line build command as
successful when only its last line succeeded, so written on two lines a failed `uv lock` is
swallowed and the release is tagged with a lockfile still naming the previous version.

## What the repository has to provide

**A deploy key that the ruleset lets through.** `main` is protected, and the release commit is a
direct push to it. It cannot be pushed as `github-actions[bot]`: that is a system bot, not an app,
and a ruleset bypass list cannot name it. A deploy key can be named, so that is what pushes.

1. `ssh-keygen -t ed25519 -C "ebpy release" -N "" -f release_key`
2. Settings → Deploy keys → Add: the contents of `release_key.pub`, **Allow write access** on.
3. Settings → Secrets and variables → Actions → New secret: `RELEASE_SSH_KEY`, the contents of
   `release_key` (the private half). Then delete both local files.
4. Settings → Rules → the ruleset protecting `main` → Bypass list → Add **Deploy keys**.

`actions/checkout` installs the key and points `origin` at SSH; `remote.ignore_token_for_push` tells
semantic-release to push over that remote rather than building a token URL of its own. `GH_TOKEN` is
still what opens the GitHub Release, which no branch rule governs. The workflow checks the secret
exists before it does anything else, because the alternative symptom is a `GH006` rejection after
the gate has already run.

Bypassing means the release push skips that ruleset entirely, required status checks included —
which is the other reason the workflow runs the whole gate itself before it calls semantic-release.

**Conventional Commits on the commits, not just the pull request titles.** Merging with a merge
commit keeps them, which is what this repository does. Switching to squash merges would make the
pull request title the only subject in the range, and it would have to follow the convention itself.

**Rebase an out-of-date pull request; never merge `main` into its branch.** The merge commit GitHub
creates when the pull request itself lands is wanted. A merge commit already inside the pull
request's head is not. In particular, do not use an **Update branch** action that is configured to
merge. Update locally instead:

```bash
git fetch origin
git rebase origin/main
git push --force-with-lease
```

python-semantic-release determines the next version by walking outward from `HEAD`, but reconstructs
the changelog with a topological log. If a branch contains its work, then a merge of a tagged `main`,
the two walks can put those pre-merge commits on opposite sides of the tag: a `feat:` still moves the
minor version while the changelog attributes it to the previous release. `quality.yml` rejects every
merge commit unique to a pull-request branch so that topology cannot reach the release job. Rebase
keeps the Conventional Commit subjects and places every branch commit unambiguously after the tag.

## Cutting 1.0.0, and re-running a release

Set `major_on_zero = true` in `pyproject.toml` and land a breaking change; the next release is
1.0.0. (Leave it `true` afterwards.)

`workflow_dispatch` re-runs the release against `main` as it stands — for a release whose push
failed. It is safe to run when there is nothing to release.

## Why every merge, and when to stop

The style this is built for: feature branch, pull request into `main`, and the merge is the release.
It fits *this* repository for reasons worth naming, because they can expire.

- **A release is cheap here.** A tag and a GitHub Release can be moved or deleted; a PyPI version
  can never be reused or withdrawn. Publishing would be the argument for batching releases — right
  now there is nothing to batch.
- **Nobody is pinned to an old minor.** Pre-1.0, with no published package, there is no user to
  support on 0.3 while `main` is on 0.5 — so there is no release branch and no backport, which is
  most of what a slower release process buys.
- **It matches what the tool argues for.** ebpy exists to make small, always-forward increments the
  only way to move; batching merges into an occasional release day would contradict the thing being
  shipped.
- **The risk it adds is the merge itself,** not the release: two pull requests green in isolation
  can break `main` together. That is why the gate re-runs before anything is tagged. A merge queue
  would catch it earlier, and is the right upgrade if `main` ever breaks this way often enough to
  notice.

Reconsider when any of that stops being true — most concretely when this starts publishing to PyPI,
or when someone depends on a version they cannot move off. The shape to move to then is a release
*pull request*: accumulate the changelog on merge, and let a human merge the release itself.
