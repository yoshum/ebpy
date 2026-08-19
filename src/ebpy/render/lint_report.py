"""Markdown rendering of the lint report, for a terminal or a CI job summary."""

from __future__ import annotations

from ..lint_report import LintReport, ReportSection


def _headline(report: LintReport) -> list[str]:
    mypy = "not measured" if report.mypy_errors is None else str(report.mypy_errors)
    return [
        f"- Files with findings: **{report.files_with_findings}**"
        if report.lint_failure is None
        else "- Lint did not run",
        f"- New violations beyond the ceiling: **{report.new_total}**",
        f"- Grandfathered backlog: **{report.backlog_total}**",
        f"- mypy errors: **{mypy}**",
        "",
    ]


def _banner(title: str, failure: str | None, consequence: str) -> list[str]:
    """A tool's complaint quoted whole. A blockquote can hold every line it wrote, so the
    reason a run failed does not have to survive being squeezed into one."""
    if failure is None:
        return []
    return [f"> **{title}**", *(f"> {line}" for line in failure.splitlines()), f"> {consequence}", ""]


def _failure_banner(report: LintReport) -> list[str]:
    """ "No debt" and "nobody looked for debt" must not render the same way."""
    return [
        *_banner(
            "Ruff did not run",
            report.lint_failure,
            "The backlog below is read from `.ebpy/baseline.json`; new violations were not measured.",
        ),
        *_banner(
            "mypy did not run",
            report.mypy_failure,
            "The type-error count below is not a measurement.",
        ),
    ]


def _new_rules(report: LintReport) -> list[str]:
    if not report.new_rules:
        return []
    return [
        "## New violations",
        "",
        "These are beyond the ceiling — new since the baseline. `ebpy check` fails on them.",
        "",
        "| Rule | Count |",
        "| --- | ---: |",
        *(f"| `{rule}` | {count} |" for rule, count in report.new_rules),
        "",
    ]


def _section(section: ReportSection) -> list[str]:
    header = f"| Rule | Total | {' | '.join(section.areas)} |"
    divider = f"| --- | ---: | {' | '.join('---:' for _ in section.areas)} |"
    return [
        f"## {section.title}",
        "",
        f"{section.total} in total.",
        "",
        header,
        divider,
        *(
            f"| `{row.rule}` | {row.total} | {' | '.join(str(count) for count in row.counts)} |"
            for row in section.rows
        ),
        "",
    ]


def render_lint_report(report: LintReport) -> str:
    lines = [
        "# Lint report",
        "",
        *_failure_banner(report),
        *_headline(report),
        *_new_rules(report),
    ]
    for section in report.sections:
        lines.extend(_section(section))
    if not report.new_rules and not report.sections:
        lines.extend(["Nothing recorded — no backlog and no new violations.", ""])
    return "\n".join(lines)
