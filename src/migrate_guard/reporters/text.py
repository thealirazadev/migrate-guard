"""Human-readable report, laid out per docs/design.md.

Color never carries meaning on its own: the severity word and the verdict text
say the same thing in plain output.
"""

from __future__ import annotations

import textwrap
from collections.abc import Sequence

from ..config import Config
from ..ir import Finding

WIDTH = 80
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
DIM = "\033[2m"


def render(
    findings: Sequence[Finding],
    files_checked: int,
    statements_checked: int,
    config: Config,
    color: bool = False,
) -> str:
    """The whole report as one string, ending with a newline."""
    lines: list[str] = []

    if files_checked == 0:
        lines.append("no migration files to check")
    else:
        current_file: str | None = None
        for finding in findings:
            if finding.span.file != current_file:
                if current_file is not None:
                    lines.append("")
                current_file = finding.span.file
                lines.append(current_file)
            lines.extend(_finding_lines(finding, color))
        if findings:
            lines.append("")
        else:
            lines.append("no problems found")
        lines.append(
            f"checked {_plural(files_checked, 'file')}, "
            f"{_plural(statements_checked, 'statement')}"
        )

    counts = summarize(findings, config.fail_on)
    if counts["total"]:
        lines.append(
            f"{_plural(counts['total'], 'finding')}: "
            f"{_plural(counts['error'], 'error')} ({counts['gating']} gating), "
            f"{_plural(counts['warning'], 'warning')}, "
            f"{counts['allowed']} allowed"
        )
    verdict = "FAIL" if counts["gating"] else "PASS"
    painted = _paint(verdict, RED if counts["gating"] else GREEN, color)
    lines.append(f"verdict: {painted} (fail_on = {config.fail_on})")

    return "\n".join(lines) + "\n"


def summarize(findings: Sequence[Finding], fail_on: str) -> dict[str, int]:
    """Counts for the summary block. Allowed findings never gate and never count as severity."""
    active = [finding for finding in findings if not finding.allowed]
    gating_severities = ("error", "warning") if fail_on == "warning" else ("error",)
    return {
        "total": len(findings),
        "error": sum(1 for finding in active if finding.severity == "error"),
        "warning": sum(1 for finding in active if finding.severity == "warning"),
        "allowed": sum(1 for finding in findings if finding.allowed),
        "gating": sum(1 for finding in active if finding.severity in gating_severities),
    }


def _finding_lines(finding: Finding, color: bool) -> list[str]:
    severity_color = RED if finding.severity == "error" else YELLOW
    prefix = (
        f"{finding.span.line:>3}  "
        f"{_paint(finding.code, CYAN, color)}  "
        f"{_paint(f'{finding.severity:<7}', severity_color, color)}  "
    )
    indent = " " * _visible_length(finding.span.line, finding.severity)
    lines = _wrap(finding.message, indent, indent)
    lines[0] = prefix + lines[0].lstrip()
    lines.append(f"{indent}statement: {_paint(finding.statement, DIM, color)}")
    if finding.allowed:
        lines.append(f'{indent}allowed: "{finding.allow_reason}"')
    else:
        lines.extend(_wrap(f"fix: {finding.safe_alternative}", indent, indent + " " * 5))
    return lines


def _wrap(body: str, initial_indent: str, subsequent_indent: str) -> list[str]:
    """Wrap on spaces only: identifiers and statements are never split mid-token."""
    return textwrap.wrap(
        body,
        width=WIDTH,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _visible_length(line: int, severity: str) -> int:
    """Message column: line number, code, and padded severity, ignoring ANSI codes."""
    return len(f"{line:>3}  ") + len("MG000  ") + len(f"{severity:<7}  ")


def _paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
