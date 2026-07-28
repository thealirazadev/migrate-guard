"""MG000 - a statement or file migrate-guard could not analyze.

Not a rule: extractors construct MG000 directly. Reporting what cannot be
understood is the honest alternative to silently assuming it is safe.
"""

from __future__ import annotations

from ..ir import Finding, SourceSpan

CODE = "MG000"
SEVERITY = "warning"
DIALECTS = ("postgres", "mysql")
SUMMARY = "statement or file that could not be analyzed"
SAFE_ALTERNATIVE = (
    "Check the statement against the configured dialect. migrate-guard reports what it "
    "cannot parse instead of assuming it is safe, so review this one by hand."
)


def diagnostic(span: SourceSpan, statement: str, message: str) -> Finding:
    return Finding(
        code=CODE,
        severity=SEVERITY,
        span=span,
        message=message,
        safe_alternative=SAFE_ALTERNATIVE,
        statement=statement,
        table=None,
    )
