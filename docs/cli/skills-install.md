# `skills install`

Install the current ebpy package's bundled Claude Code skills in the project's
`.claude/skills` directory:

Run it through the project's package manager, for example `uv run ebpy skills install`,
`poetry run ebpy skills install`, `pdm run ebpy skills install` or
`pipenv run ebpy skills install`.

This is the second stage of [`ebpy install`](install.md). It is public so the skills can be restored
or updated from the dependency already selected by the project's metadata and lockfile, without
resolving another ebpy source.

The managed entries are the five `ebpy-*` skill directories and `_shared`. Unrelated project skills
are never touched. Re-running with identical files is safe. If a managed entry differs, the command
refuses to overwrite it; review the local edit and use `--force` only when it should be replaced:

Append `--force` to the manager-specific command when replacement is intentional.

The installed version, source and file hashes are recorded in
`.claude/skills/.ebpy-manifest.json`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | skills installed |
| `1` | no project root, a managed skill conflict, or missing bundled skills |
