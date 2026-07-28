"""Raw SQL extraction on sqlglot.

The file is tokenized once so statements can be split on semicolons with their
true starting line, then each statement is parsed on its own: one unparseable
statement becomes an MG000 diagnostic and the rest of the file still gets
checked.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import Token, TokenType

from ..ir import Finding, Operation, OpKind, SourceSpan, excerpt
from ..rules import mg000
from . import ExtractionResult


def extract(path: str, text: str, dialect: str) -> ExtractionResult:
    """Map one SQL file to operations plus MG000 diagnostics."""
    try:
        statements = _split(text, dialect)
    except TokenError:
        span = SourceSpan(file=path, line=1)
        return ExtractionResult(
            diagnostics=(
                mg000.diagnostic(
                    span,
                    excerpt(text),
                    f"{path} could not be tokenized as {dialect} SQL, so no statement in it "
                    "was checked.",
                ),
            )
        )

    operations: list[Operation] = []
    diagnostics: list[Finding] = []
    for statement, line in statements:
        span = SourceSpan(file=path, line=line)
        raw = excerpt(statement)
        try:
            expression = sqlglot.parse_one(
                statement, read=dialect, error_level=sqlglot.ErrorLevel.RAISE
            )
        except (ParseError, TokenError):
            diagnostics.append(
                mg000.diagnostic(
                    span,
                    raw,
                    f"Statement could not be parsed as {dialect} SQL, so migrate-guard could "
                    "not check it.",
                )
            )
            continue
        operations.extend(_operations(expression, span, raw))

    return ExtractionResult(
        operations=tuple(operations),
        diagnostics=tuple(diagnostics),
        statement_count=len(statements),
    )


def _split(text: str, dialect: str) -> list[tuple[str, int]]:
    """Split on semicolon tokens, keeping each statement's first line number."""
    groups: list[list[Token]] = []
    current: list[Token] = []
    for token in sqlglot.tokenize(text, read=dialect):
        if token.token_type is TokenType.SEMICOLON:
            if current:
                groups.append(current)
                current = []
            continue
        current.append(token)
    if current:
        groups.append(current)
    return [(text[group[0].start : group[-1].end + 1], group[0].line) for group in groups]


def _operations(expression: exp.Expression, span: SourceSpan, raw: str) -> list[Operation]:
    if isinstance(expression, exp.Create):
        return _create(expression, span, raw)
    if isinstance(expression, exp.Drop):
        return _drop(expression, span, raw)
    if isinstance(expression, exp.Alter):
        return _alter(expression, span, raw)
    return []


def _create(expression: exp.Create, span: SourceSpan, raw: str) -> list[Operation]:
    kind = str(expression.args.get("kind") or "").upper()
    if kind == "TABLE":
        return [
            Operation(kind=OpKind.create_table, span=span, raw=raw, table=_table(expression)),
        ]
    if kind == "INDEX":
        return [
            Operation(
                kind=OpKind.create_index,
                span=span,
                raw=raw,
                table=_table(expression),
                details={
                    "unique": bool(expression.args.get("unique")),
                    "concurrent": bool(expression.args.get("concurrently")),
                },
            )
        ]
    return []


def _drop(expression: exp.Drop, span: SourceSpan, raw: str) -> list[Operation]:
    kind = str(expression.args.get("kind") or "").upper()
    if kind == "TABLE":
        return [Operation(kind=OpKind.drop_table, span=span, raw=raw, table=_table(expression))]
    return []


def _alter(expression: exp.Alter, span: SourceSpan, raw: str) -> list[Operation]:
    table = _table(expression)
    operations: list[Operation] = []
    for action in expression.args.get("actions") or []:
        if isinstance(action, exp.Drop) and str(action.args.get("kind") or "").upper() == "COLUMN":
            operations.append(
                Operation(
                    kind=OpKind.drop_column,
                    span=span,
                    raw=raw,
                    table=table,
                    column=_name(action.this),
                )
            )
    return operations


def _table(expression: exp.Expression) -> str | None:
    table = expression.find(exp.Table)
    return table.name if table is not None else None


def _name(node: exp.Expression | None) -> str | None:
    return node.name if node is not None and node.name else None
