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

## Failure safety

The command writes the complete new bundle and manifest into a temporary directory before touching
the installed skills. It then moves the previous managed entries into a backup and replaces only
those entries; unrelated project skills remain in place. If a filesystem operation fails during the
swap, newly moved entries are removed and the backup is restored.

When rollback succeeds, the error confirms that the previous managed skills were restored. If
rollback itself encounters an error, the temporary directory is deliberately retained and its path
is printed so the remaining backup can be recovered manually. This protects handled filesystem
failures; it is not a persistent transaction journal for abrupt process or machine termination.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | skills installed |
| `1` | no project root, a managed skill conflict, an inspection error, missing bundled skills, or a staging/swap failure |
