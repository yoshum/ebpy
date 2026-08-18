# Resolve the ebpy command

Complete this step before running the first `ebpy` command from any skill. In the individual skill
files, `ebpy` is a placeholder for the invocation selected here, not necessarily a bare executable.

1. Detect the project's Python environment and package runner from its lockfile and configuration.
2. Check whether `ebpy` is installed in that environment with a read-only invocation such as
   `uv run ebpy --help`, `poetry run ebpy --help`, `pdm run ebpy --help`, or
   `pipenv run ebpy --help`. If it is, use that runner for every later `ebpy` command. An executable
   found only outside the project environment does not count.
3. If it is not installed, stop and ask the user to add `ebpy` to the project's development
   dependencies with that package manager. Pin it to the same Git tag or commit as the installed
   copy of these skills so their instructions and the command stay compatible. Show the exact
   install command and explain why the version must match. If the skills' source ref cannot be
   determined, ask which ref to pin instead of guessing. Do not install it without approval.
4. If the user approves, install it and use the project's runner. If the user refuses, use
   `uvx --from "git+https://github.com/yoshum/ebpy" ebpy` for every later `ebpy` command.

Keep the selected invocation for the whole task. Do not silently switch between the project
environment, a global executable, and `uvx`.
