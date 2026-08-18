"""ebpy — make a Python codebase that can only get better."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .commands.bootstrap import run_bootstrap
from .commands.catalog import run_catalog
from .commands.check import run_check
from .commands.diagnose import run_diagnose
from .commands.freeze import run_freeze
from .commands.log import LOG_KIND_LIST, is_log_kind, run_log
from .commands.next_command import run_next
from .commands.prune import run_prune
from .commands.report import run_report
from .commands.secrets import run_secrets
from .commands.status import run_status
from .generate.workflows import DEFAULT_PYTHON_VERSION
from .ruff_runner import RuffFailedError, RuffNotFoundError

USAGE_EPILOG = f"""\
commands:
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
    output: str
    code: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ebpy",
        description="Make a Python codebase that can only get better.",
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

    bootstrap = add("bootstrap", "install missing tooling")
    bootstrap.add_argument("--dry-run", action="store_true", help="print the plan without touching anything")
    bootstrap.add_argument(
        "--python", default=DEFAULT_PYTHON_VERSION, help="python version for the generated workflow"
    )

    freeze = add("freeze", "pin today's violations as the ceiling")
    freeze.add_argument("--force", action="store_true", help="allow a ceiling to move up")

    add("prune", "reclaim the ceiling you earned")

    check = add("check", "CI gate")
    check.add_argument("--no-write", action="store_true", help="do not update the ledger")

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


def _check_outcome(args: argparse.Namespace, cwd: Path) -> Outcome:
    result = run_check(cwd, write=not args.no_write)
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
    return Outcome(run_log(cwd, args.kind, text, args.rule), 0)


# Every command that only ever succeeds; `check`, `secrets` and `log` are the three that
# can fail, above.
_ALWAYS_OK: dict[str, Callable[[argparse.Namespace, Path], str]] = {
    "diagnose": lambda args, cwd: run_diagnose(cwd, args.json, args.write),
    "bootstrap": lambda args, cwd: run_bootstrap(cwd, args.dry_run, args.python),
    "freeze": lambda args, cwd: run_freeze(cwd, args.force),
    "prune": lambda _args, cwd: run_prune(cwd),
    "status": lambda args, cwd: run_status(cwd, args.json),
    "next": lambda args, cwd: run_next(cwd, args.json, args.fan_in),
    "report": lambda args, cwd: run_report(cwd, args.json),
    "catalog": lambda _args, cwd: run_catalog(cwd),
}

_FALLIBLE: dict[str, Callable[[argparse.Namespace, Path], Outcome]] = {
    "check": _check_outcome,
    "secrets": _secrets_outcome,
    "log": _log_outcome,
}


def _dispatch(args: argparse.Namespace, cwd: Path) -> Outcome:
    always_ok = _ALWAYS_OK.get(args.command)
    if always_ok:
        return Outcome(always_ok(args, cwd), 0)
    fallible = _FALLIBLE.get(args.command)
    if fallible:
        return fallible(args, cwd)
    return Outcome(f"Unknown command: {args.command}", 1)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    cwd = Path(args.cwd).resolve()
    try:
        outcome = _dispatch(args, cwd)
    except (RuffNotFoundError, RuffFailedError) as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(f"{outcome.output}\n")
    return outcome.code


if __name__ == "__main__":
    raise SystemExit(main())
