"""Markdown rendering of the analysis report, for a terminal or a CI job summary."""

from __future__ import annotations

from ..analysis_report import AnalysisReport, ReportSection


def _analyzer_table(report: AnalysisReport) -> list[str]:
    lines = [
        "## Analyzers",
        "",
        "| Analyzer | In contract | Status | Findings | Files |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for name, summary in report.analyzers:
        in_contract = "yes" if summary.in_contract else "no"
        findings = "not measured" if summary.findings is None else str(summary.findings)
        files = "not measured" if summary.files_with_findings is None else str(summary.files_with_findings)
        lines.append(f"| `{name}` | {in_contract} | {summary.status} | {findings} | {files} |")
    lines.append("")
    return lines


def _headline(report: AnalysisReport) -> list[str]:
    return [
        f"- New violations beyond the ceiling: **{report.new_total}**",
        f"- Grandfathered backlog: **{report.backlog_total}**",
        "",
    ]


def _banner(title: str, failure: str, consequence: str) -> list[str]:
    """A tool's complaint quoted whole. A blockquote can hold every line it wrote, so the
    reason a run failed does not have to survive being squeezed into one."""
    return [f"> **{title}**", *(f"> {line}" for line in failure.splitlines()), f"> {consequence}", ""]


def _failure_banners(report: AnalysisReport) -> list[str]:
    """One blockquote per failing contract analyzer.

    "No debt" and "nobody looked" must not render the same way.
    """
    lines: list[str] = []
    for name, summary in report.analyzers:
        if not summary.in_contract:
            continue
        if summary.failure is not None:
            consequence = (
                f"The backlog for {name} below is read from `.ebpy/baseline.json`;"
                " new violations were not measured."
            )
            lines.extend(_banner(f"{name} did not run", summary.failure, consequence))
    return lines


def _new_rules(report: AnalysisReport) -> list[str]:
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


def _unratcheted_section(report: AnalysisReport) -> list[str]:
    """Complete non-contract analyzers that ran — excluded from new and backlog."""
    unratcheted = [
        (name, summary)
        for name, summary in report.analyzers
        if not summary.in_contract and summary.status == "complete"
    ]
    if not unratcheted:
        return []
    lines = ["## Unratcheted analyzers", ""]
    for name, summary in unratcheted:
        # A complete analyzer is always Measured, so its counts are real numbers, never the
        # None that stands for "not measured" — rendering them as 0 would erase that distinction.
        assert summary.findings is not None and summary.files_with_findings is not None
        line = f"- `{name}`: {summary.findings} finding(s) across "
        lines.append(f"{line}{summary.files_with_findings} file(s), not under contract")
    lines.append("")
    return lines


def render_analysis_report(report: AnalysisReport) -> str:
    lines = [
        "# Analysis report",
        "",
        *_failure_banners(report),
        *_analyzer_table(report),
        *_headline(report),
        *_new_rules(report),
    ]
    for section in report.sections:
        lines.extend(_section(section))
    lines.extend(_unratcheted_section(report))
    if not report.new_rules and not report.sections:
        lines.extend(["Nothing recorded — no backlog and no new violations.", ""])
    return "\n".join(lines)
