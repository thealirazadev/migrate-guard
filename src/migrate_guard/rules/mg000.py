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
EXPLANATION = """MG000 is a diagnostic, not a rule: it marks a statement or a file that
migrate-guard could not analyse.

It appears when a statement does not parse under the configured dialect, when a whole
file cannot be tokenized, or when a framework migration contains a schema change whose
arguments are not literals and therefore cannot be read without running the code.

The common causes are a dialect mismatch (MySQL backticks checked as postgres, or the
reverse), vendor syntax the parser does not model, and a stray character that turns
the rest of the file into one unparseable statement.

MG000 is a warning: it does not gate a build unless fail_on = "warning". It is
deliberately not ignorable through the config ignore list, because a statement nobody
checked is exactly the one worth looking at. Read the statement it names, decide
whether it is safe, and record that decision:

    -- migrate-guard: allow MG000 reason="vendor-specific hint, reviewed by hand"
"""


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
