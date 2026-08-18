# `install`

Add an exact ebpy release or Git ref to the current uv project's development dependencies, then
delegate skill installation to that dependency's [`ebpy skills install`](skills-install.md). The
instructions and CLI therefore come from the same installed revision.

## Default: the bootstrap command's release

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install
```

The Git checkout is only the bootstrap command. `install` reads its own package version and adds the
corresponding `v<version>` tag as the project dependency; a moving `main` branch is never persisted
in `pyproject.toml`. It then runs the installed command through uv:

```bash
uv run ebpy skills install
```

## A particular release

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install <version>
```

Both `1.2.3` and `v1.2.3` select the `v1.2.3` Git tag. Only exact versions are accepted; ranges such
as `>=1.2,<2` are rejected before `uv add` runs.

## A commit or branch

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install --ref <commit-or-branch>
```

The ref is recorded as a Git dependency and `uv.lock` records the resolved commit. `VERSION` and
`--ref` cannot be used together.

## Existing skills

If a managed skill differs from the installed package, the delegated command leaves it unchanged
and exits with an error. Review the local edit, then replace it deliberately with:

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install --force
```

`--force` is passed only to `ebpy skills install`; it does not change dependency resolution.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | dependency and skills installed |
| `1` | invalid version/ref, no project root, `uv add` failure, or delegated skill installation failure |
