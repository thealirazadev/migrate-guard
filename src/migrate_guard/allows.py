"""Inline allow comments: parsing, and applying every waiver to a file's findings.

The grammar is the contract in docs/api-contracts.md:

    <comment-marker> migrate-guard: allow CODE[,CODE...] reason="<justification>"

A malformed allow aborts the run (exit 2) instead of being skipped, because a
suppression that half-works is worse than none. Parsing is line based and never
evaluates the file.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from .config import Config, ConfigAllow, MigrateGuardError, known_codes
from .ir import Allow, Finding, SourceSpan

# Comment markers accepted per input format.
MARKERS = {
    # `#` is a comment in MySQL; on Postgres it is never valid SQL before this text anyway.
    "sql": ("--", "#"),
    "laravel": ("//", "#"),
    "django": ("#",),
}

SOURCE_INLINE = "inline"
SOURCE_CONFIG = "config"

_DIRECTIVE = re.compile(r"(?P<marker>--|//|#)\s*migrate-guard:(?P<rest>.*)$")
_ALLOW = re.compile(r"^\s*allow\s+(?P<codes>[^\s=,]+(?:\s*,\s*[^\s=,]+)*)(?P<tail>.*)$")
_REASON = re.compile(r'^\s+reason="(?P<reason>[^"]*)"\s*$')
_CODE = re.compile(r"^MG\d{3}$")

NO_REASON_REMEDY = 'add reason="..." with a short justification to the allow comment'


def parse_inline(path: str, text: str, fmt: str) -> tuple[Allow, ...]:
    """Every inline allow in one file, in line order. Raises MigrateGuardError if malformed."""
    markers = MARKERS.get(fmt, ())
    codes_known = known_codes()
    allows: list[Allow] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _DIRECTIVE.search(line)
        if match is None or match["marker"] not in markers:
            continue
        where = f"{path}:{number}"
        allow = _ALLOW.match(match["rest"])
        if allow is None:
            raise MigrateGuardError(
                f"cannot parse the migrate-guard comment at {where}",
                'expected: migrate-guard: allow CODE[,CODE...] reason="..."',
            )
        codes = tuple(code.strip() for code in allow["codes"].split(","))
        for code in codes:
            if not _CODE.match(code) or code not in codes_known:
                raise MigrateGuardError(
                    f'unknown rule code "{code}" in the allow comment at {where}',
                    "run migrate-guard rules for the list",
                )
        reason = _REASON.match(allow["tail"])
        if reason is None:
            if "reason=" in allow["tail"]:
                raise MigrateGuardError(
                    f"cannot parse the reason in the allow comment at {where}",
                    'write it as reason="..." at the end of the comment',
                )
            raise MigrateGuardError(f"allow comment at {where} has no reason", NO_REASON_REMEDY)
        if not reason["reason"].strip():
            raise MigrateGuardError(f"allow comment at {where} has no reason", NO_REASON_REMEDY)
        allows.append(
            Allow(
                codes=codes,
                reason=reason["reason"].strip(),
                span=SourceSpan(file=path, line=number),
                source=SOURCE_INLINE,
            )
        )
    return tuple(allows)


def apply(
    findings: Sequence[Finding],
    path: str,
    inline: Sequence[Allow],
    config: Config,
    warnings: list[str],
) -> list[Finding]:
    """Drop ignored codes, then mark findings waived by inline allows, then config allows.

    An inline allow waives the findings with a listed code raised by the first operation
    at or after its line that has such a finding. A config allow waives the listed codes
    anywhere in its file. An allow that waives nothing adds a message to `warnings`.
    """
    result = [finding for finding in findings if finding.code not in config.ignore]

    for allow in sorted(inline, key=lambda a: a.span.line):
        candidates = [
            index
            for index, finding in enumerate(result)
            if not finding.allowed
            and finding.code in allow.codes
            and finding.span.line >= allow.span.line
        ]
        if not candidates:
            warnings.append(
                f"allow comment at {allow.span.file}:{allow.span.line} matches no finding"
            )
            continue
        target_line = min(result[index].span.line for index in candidates)
        for index in candidates:
            if result[index].span.line == target_line:
                result[index] = replace(result[index], allowed=True, allow_reason=allow.reason)

    for entry in config.allow:
        if not _same_file(entry, path):
            continue
        matched = False
        for index, finding in enumerate(result):
            if not finding.allowed and finding.code in entry.rules:
                result[index] = replace(finding, allowed=True, allow_reason=entry.reason)
                matched = True
        if not matched:
            warnings.append(
                f"config allow for {entry.file} ({', '.join(entry.rules)}) matches no finding"
            )

    return result


def _same_file(entry: ConfigAllow, path: str) -> bool:
    """Config allow paths are relative to the working directory, like `paths`."""
    return Path(entry.file).resolve() == Path(path).resolve()
