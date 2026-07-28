"""Running the registered rules over one file's operations.

The new-table exemption lives here rather than in each rule: a table created in
the same file has no rows and no traffic, so no operation on it can lock or
rewrite anything that matters. Centralizing it removes the largest class of
false positives in one place.
"""

from __future__ import annotations

from collections.abc import Sequence

from .config import Config
from .extractors import ExtractionResult
from .ir import Finding, Operation, OpKind
from .rules import rules_for


def check_file(result: ExtractionResult, config: Config) -> list[Finding]:
    """Findings for one file: its diagnostics plus every applicable rule's verdict."""
    operations = result.operations
    new_tables = _tables_created_here(operations)
    findings = list(result.diagnostics)
    rules = rules_for(config.dialect)

    for index, op in enumerate(operations):
        if op.table is not None and op.table.casefold() in new_tables:
            continue
        for rule in rules:
            finding = rule.check(op, operations, index, config)
            if finding is not None:
                findings.append(finding)

    return sort_findings(findings)


def sort_findings(findings: Sequence[Finding]) -> list[Finding]:
    """Deterministic report order: file, then line, then rule code."""
    return sorted(findings, key=lambda f: (f.span.file, f.span.line, f.code))


def _tables_created_here(operations: Sequence[Operation]) -> set[str]:
    return {
        op.table.casefold()
        for op in operations
        if op.kind is OpKind.create_table and op.table is not None
    }
