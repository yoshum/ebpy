# `ebpy secrets`

Runs `gitleaks` over the **history and the working tree** and fails on any finding.

```bash
ebpy secrets
```

Requires `gitleaks` on the path. The [generated workflow](../defaults.md#githubworkflowssecret-scanyml) installs a
pinned, digest-checked release; locally, install it however you install tools.

## Why both scans

Either alone passes a repository that is holding a secret:

- the **history** scan misses the key you pasted an hour ago and have not committed;
- the **working tree** scan misses the key that was committed and then deleted — which is still in
  every clone.

The working-tree scan honours `.gitignore`, so a virtualenv costs nothing.

## This is the one thing here with no baseline

Every other rule records what exists and holds the line. A committed key is already public, so there
is nothing to grandfather and the fix is **rotation**, not a commit. If the scan fires, rotate the
credential first and clean the history second.

## Three answers, not two

gitleaks reports a finding and its own failure with the same exit code unless asked otherwise, so
ebpy separates them:

| | |
| --- | --- |
| clean | exit **0** |
| secrets found | exit **2**, and the finding, redacted |
| the scan could not run | exit **1**, saying so — not a clean result |

That last row matters more than it looks. Outside a git work tree, `gitleaks git` logs an error,
scans **zero commits**, and exits 0 with "no leaks found" — a clean bill of health for a scan that
read nothing. ebpy checks for a repository first and refuses instead. A missing `gitleaks` binary is
reported the same way rather than being treated as a pass.

Findings are always **redacted**, so a secret never lands in a public CI log.
