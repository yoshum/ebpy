"""ebpy — make a codebase that can only get better."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .commands.bootstrap import run_bootstrap
from .commands.catalog import run_catalog
from .commands.check import run_check
from .commands.diagnose import run_diagnose
from .commands.freeze import run_freeze
from .commands.install import run_install
from .commands.log import LOG_KIND_LIST, is_log_kind, run_log
from .commands.next_command import run_next
from .commands.prune import run_prune
from .commands.report import run_report
from .commands.secrets import run_secrets
from .commands.skills_install import run_skills_install
from .commands.status import run_status
from .errors import CommandError
from .generate.workflows import DEFAULT_PYTHON_VERSION
from .tools import ANALYZER_NAMES

if TYPE_CHECKING:
    from collections.abc import Callable

USAGE_EPILOG = f"""\
commands:
  install     add an exact ebpy release/ref and its skills to this project
  skills      manage the bundled Claude Code skills
  diagnose    survey the repo and write QUALITY.md   (read-only without --write)
  bootstrap   install missing tooling, generate configs
  freeze      pin today's violations as the ceiling   (once, at the start)
  prune       reclaim the ceiling you earned          (lowers it)
  check       fail if anything rose above its ceiling (for CI)
  status      print the current backlog
  next        what to drain first, and what each one enforces
  report      where the findings are, by rule and area (markdown, for CI)
  secrets     scan the whole history for committed credentials (gitleaks)
  catalog     list the helpers that already exist, so nobody writes a sixth
  log         record what happened, stamped with the current commit

Python {DEFAULT_PYTHON_VERSION} is the default for generated workflows.
"""


@dataclass(frozen=True)
class Outcome:
    """A command's result as data: the text to print and the exit code to return."""

    output: str
    code: int


class _Result(Protocol):
    @property
    def ok(self) -> bool: ...

    @property
    def message(self) -> str: ...


def build_parser() -> argparse.ArgumentParser:
    """Build the ebpy argument parser, repeating the global --cwd/--json flags after each subcommand."""
    parser = argparse.ArgumentParser(
        prog="ebpy",
        description="Make a codebase that can only get better.",
        epilog=USAGE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--cwd", default=".", help="target repository (default: current directory)")
    parser.add_argument("--json", action="store_true", help="machine-readable output where supported")

    # The same two flags after the subcommand, which is where anybody would type them.
    # SUPPRESS rather than a default, so an unpassed flag leaves the value the top-level
    # parser already resolved instead of overwriting it with a fresh default.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--cwd", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="command", metavar="command", parser_class=argparse.ArgumentParser)

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_text, parents=[common])

    diagnose = add("diagnose", "survey the repo")
    diagnose.add_argument("--write", action="store_true", help="persist state and QUALITY.md")

    install = add("install", "install an exact ebpy release/ref and its Claude Code skills")
    install.add_argument(
        "version",
        nargs="?",
        metavar="VERSION",
        help="exact release version (default: this installer's version)",
    )
    install.add_argument("--ref", help="install an exact Git commit or branch instead of a release")
    install.add_argument(
        "--force", action="store_true", help="replace locally changed ebpy skill directories"
    )

    skills = add("skills", "manage the bundled Claude Code skills")
    skills_sub = skills.add_subparsers(dest="skills_command", metavar="command", required=True)
    skills_install = skills_sub.add_parser(
        "install", help="install bundled skills into .claude/skills", parents=[common]
    )
    skills_install.add_argument(
        "--force", action="store_true", help="replace locally changed ebpy skill directories"
    )

    bootstrap = add("bootstrap", "install missing tooling")
    bootstrap.add_argument("--dry-run", action="store_true", help="print the plan without touching anything")
    bootstrap.add_argument(
        "--python", default=DEFAULT_PYTHON_VERSION, help="python version for the generated workflow"
    )

    freeze = add("freeze", "pin today's violations as the ceiling")
    freeze.add_argument("--force", action="store_true", help="re-pin over an existing or unreadable contract")
    freeze.add_argument(
        "--analyzer",
        choices=sorted(ANALYZER_NAMES),
        default=None,
        help="pin one analyzer's ceiling, leaving every other analyzer untouched",
    )

    add("prune", "reclaim the ceiling you earned")

    check = add("check", "CI gate")
    check.add_argument("--no-write", action="store_true", help="do not update the ledger")
    check.add_argument(
        "--analyzer",
        choices=sorted(ANALYZER_NAMES),
        default=None,
        help="check only this analyzer, leaving every other analyzer untouched",
    )

    add("status", "print the current backlog")

    next_cmd = add("next", "what to drain first")
    next_cmd.add_argument(
        "--fan-in",
        action="store_true",
        help="also count how many files import each one (reads every source file)",
    )

    add("report", "the backlog by rule and area")
    add("secrets", "scan for committed credentials")
    add("catalog", "list the helpers that already exist")

    log = add("log", "record what happened")
    log.add_argument("--kind", default="note", help=LOG_KIND_LIST)
    log.add_argument("--rule", default=None, help="the rule this entry is about")
    log.add_argument("text", nargs="*", help="what happened")

    return parser


def _result_outcome(result: _Result) -> Outcome:
    return Outcome(result.message, 0 if result.ok else 1)


def _secrets_outcome(_args: argparse.Namespace, cwd: Path) -> Outcome:
    # Carries gitleaks' own code — 2 findings, 1 could-not-scan — because flattening both
    # to 1 is the ambiguity this command exists to remove, and a caller cannot get the
    # distinction back.
    verdict = run_secrets(cwd)
    return Outcome(verdict.message, verdict.code)


def _log_outcome(args: argparse.Namespace, cwd: Path) -> Outcome:
    if not is_log_kind(args.kind):
        return Outcome(f"--kind must be one of: {LOG_KIND_LIST}", 1)
    text = " ".join(args.text).strip()
    if not text:
        return Outcome('log needs text: ebpy log --kind deferred "..."', 1)
    # An outcome command carries its exit status as data rather than raising, so a
    # malformed --rule — refused by run_log itself, closer to the concept it names — is
    # converted here rather than left to propagate past this function's declared return type.
    try:
        return Outcome(run_log(cwd, args.kind, text, args.rule), 0)
    except CommandError as error:
        return Outcome(str(error), 1)


# Text commands return normally on success and raise CommandError when a request must
# be refused. Result and outcome commands carry their exit status as data instead.
_TEXT_COMMANDS: dict[str, Callable[[argparse.Namespace, Path], str]] = {
    "bootstrap": lambda args, cwd: run_bootstrap(cwd, args.dry_run, args.python),
    "catalog": lambda _args, cwd: run_catalog(cwd),
    "diagnose": lambda args, cwd: run_diagnose(cwd, args.json, args.write),
    "freeze": lambda args, cwd: run_freeze(cwd, args.force, args.analyzer),
    "prune": lambda _args, cwd: run_prune(cwd),
    "status": lambda args, cwd: run_status(cwd, args.json),
    "next": lambda args, cwd: run_next(cwd, args.json, args.fan_in),
    "report": lambda args, cwd: run_report(cwd, args.json),
}

_RESULT_COMMANDS: dict[str, Callable[[argparse.Namespace, Path], _Result]] = {
    "install": lambda args, cwd: run_install(cwd, args.version, args.ref, args.force),
    "skills": lambda args, cwd: run_skills_install(cwd, args.force),
    "check": lambda args, cwd: run_check(cwd, write=not args.no_write, analyzer=args.analyzer),
}

_OUTCOME_COMMANDS: dict[str, Callable[[argparse.Namespace, Path], Outcome]] = {
    "secrets": _secrets_outcome,
    "log": _log_outcome,
}


def _dispatch(args: argparse.Namespace, cwd: Path) -> Outcome:
    text_command = _TEXT_COMMANDS.get(args.command)
    if text_command:
        return Outcome(text_command(args, cwd), 0)
    result_command = _RESULT_COMMANDS.get(args.command)
    if result_command:
        return _result_outcome(result_command(args, cwd))
    outcome_command = _OUTCOME_COMMANDS.get(args.command)
    if outcome_command:
        return outcome_command(args, cwd)
    return Outcome(f"Unknown command: {args.command}", 1)


def main(argv: list[str] | None = None) -> int:
    """Parse argv, dispatch the subcommand, and return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    cwd = Path(args.cwd).resolve()
    try:
        outcome = _dispatch(args, cwd)
    except CommandError as error:
        sys.stdout.write(f"{error}\n")
        return 1
    sys.stdout.write(f"{outcome.output}\n")
    return outcome.code


if __name__ == "__main__":
    raise SystemExit(main())
