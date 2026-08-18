# `install`

Add an ebpy release or Git ref with the project's detected package manager, then delegate skill
installation to that dependency's [`ebpy skills install`](skills-install.md). The instructions and
CLI therefore come from the same installed revision.

## Default: the release recorded on `main`

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install
```

The Git checkout is the bootstrap command. When its `--from` URL has no explicit ref, `install`
reads `ebpy.__version__` from `main` and adds the corresponding `v<version>` tag. It does not query a
release API. A release older than v0.3.0 is rejected before any dependency command runs because it
does not provide `ebpy skills install`.

## Target precedence

The first available target wins:

1. `VERSION` or `--ref` passed directly to `ebpy install`
2. a ref explicitly present in the bootstrap `--from` Git URL
3. the `v<ebpy.__version__>` release tag recorded on `main`

Thus a bootstrap ref is preserved rather than silently replaced:

```bash
uvx --from "git+https://github.com/yoshum/ebpy@<commit-or-branch>" ebpy install
```

Use a CLI argument when the bootstrap source and installed target should differ.

## A particular release

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install <version>
```

Both `1.2.3` and `v1.2.3` select the `v1.2.3` Git tag. Only exact versions are accepted; ranges such
as `>=1.2,<2` are rejected before the project changes. A value such as `main` explains that
`--ref main` should be used instead.

## A commit or branch

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install --ref <commit-or-branch>
```

`VERSION` and `--ref` cannot be used together. Version-like refs below v0.3.0 are rejected. An
arbitrary commit cannot be classified by version before it is installed; it must itself provide
`ebpy skills install`.

## Package manager

The lockfile or `pyproject.toml` configuration selects both commands:

| Detected manager | Add dependency | Install skills |
| --- | --- | --- |
| uv | `uv add --dev ...` | `uv run ebpy skills install` |
| Poetry | `poetry add --group dev ...` | `poetry run ebpy skills install` |
| PDM | `pdm add -d ...` | `pdm run ebpy skills install` |
| Pipenv | `pipenv install --dev --editable ...` | `pipenv run ebpy skills install` |
| pip fallback | `pip install ...` | `ebpy skills install` |

The first four persist the dependency in project metadata and a lockfile. The pip fallback installs
into the active environment because pip has no standard project-level development dependency
declaration.

## Existing skills

Empty managed directories and unchanged files from a previous ebpy manifest are safe to replace.
If a managed skill was edited locally, the delegated command leaves it unchanged and exits with an
error. Review the edit, then replace it deliberately with:

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install --force
```

`--force` is passed only to `ebpy skills install`; it does not change dependency resolution.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | dependency and skills installed |
| `1` | invalid or unsupported target, no project root, dependency failure, or delegated skill installation failure |
