"""Markdown rendering of the analysis report, for a terminal or a CI job summary."""

from __future__ import annotations

from ..decide.analysis_report import AnalysisReport, AnalyzerSummary, ReportSection


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


def _incomplete_detail(summary: AnalyzerSummary) -> str:
    """The unparsed files an incomplete run left behind, named the way `check` names them.

    An incomplete analyzer has no `failure` string — the run started and produced cells —
    so its complaint is the list of files it could not parse, not a tool error message.
    """
    samples = [f"{u.file}:{u.line}  {u.message}" for u in summary.unattributed]
    more = summary.unattributed_total - len(samples)
    lines = [f"{summary.unattributed_total} syntax error(s) left files unparsed:", *samples]
    if more > 0:
        lines.append(f"+ {more} more")
    return "\n".join(lines)


def _consequence(name: str, in_contract: bool) -> str:
    """What an unmeasured analyzer means for the numbers below, which turns on the contract.

    An analyzer under contract has a ceiling: the backlog falls back to what the baseline
    already recorded, and this run measured no new violations against it. One outside the
    contract has no ceiling at all, so there is no backlog to fall back to — the run simply
    produced no numbers for it. "Nobody looked" must read the same either way; only what
    that costs the report differs.
    """
    if in_contract:
        return (
            f"The backlog for {name} below is read from `.ebpy/baseline.json`;"
            " new violations were not measured."
        )
    return f"{name} has no ceiling yet, so this run recorded no numbers for it."


def _failure_banners(report: AnalysisReport) -> list[str]:
    """One blockquote per analyzer that could not be fully measured, in or out of contract.

    "No debt" and "nobody looked" must not render the same way, so a failed run quotes its
    tool error and an incomplete one names the files it could not parse — a failure reason is
    worth showing whether or not the analyzer has a ceiling. Only the consequence differs: a
    contract analyzer's backlog fell back to the baseline, while one outside the contract has
    no ceiling for the report to speak to at all.
    """
    lines: list[str] = []
    for name, summary in report.analyzers:
        consequence = _consequence(name, summary.in_contract)
        if summary.failure is not None:
            lines.extend(_banner(f"{name} did not run", summary.failure, consequence))
        elif summary.status == "no-runner":
            # A contract analyzer this build has no runner for: no tool detail to quote.
            # Name the missing runner so it is not silently rendered as a bare status.
            lines.extend(
                _banner(f"{name} did not run", f"{name} has no runner in this ebpy build", consequence)
            )
        elif summary.status == "incomplete":
            lines.extend(
                _banner(f"{name} could not lint every file", _incomplete_detail(summary), consequence)
            )
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
