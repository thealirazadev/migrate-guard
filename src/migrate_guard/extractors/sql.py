"""Raw SQL extraction on sqlglot.

The file is tokenized once so statements can be split on semicolons with their
true starting line, then each statement is parsed on its own: one unparseable
statement becomes an MG000 diagnostic and the rest of the file still gets
checked.

sqlglot models most ALTER forms as an `Alter` node with typed actions, but a few
Postgres forms fall back to a generic `Command` holding the raw tail. The two
that matter to the rules (VALIDATE CONSTRAINT and ADD CONSTRAINT ... UNIQUE
USING INDEX) are recovered from that tail with anchored, bounded regexes;
everything else a `Command` covers stays unmapped rather than guessed at. An
ALTER TABLE that lands there is still reported as MG000, because a multi-action
ALTER hides drops and rewrites and silence would read as a clean bill of health.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import Token, TokenType

from ..ir import Finding, Operation, OpKind, SourceSpan, excerpt
from ..rules import mg000
from . import ExtractionResult

IDENTIFIER = r'[\w."`]{1,128}'
VALIDATE_CONSTRAINT = re.compile(
    rf"^TABLE\s+(?:ONLY\s+)?(?P<table>{IDENTIFIER})"
    rf"\s+VALIDATE\s+CONSTRAINT\s+(?P<name>{IDENTIFIER})\s*$",
    re.IGNORECASE,
)
UNIQUE_USING_INDEX = re.compile(
    rf"^TABLE\s+(?:ONLY\s+)?(?P<table>{IDENTIFIER})"
    rf"\s+ADD\s+CONSTRAINT\s+(?P<name>{IDENTIFIER})"
    rf"\s+UNIQUE\s+USING\s+INDEX\s+{IDENTIFIER}\s*$",
    re.IGNORECASE,
)
ALTER_TABLE_TAIL = re.compile(r"^TABLE\s", re.IGNORECASE)

# A default is metadata-only on Postgres 11+ only when it is a constant
# expression. Anything built from a function or a subquery is treated as
# volatile, so an unrecognized default errs toward a finding.
CONSTANT_NODES = (
    exp.Literal,
    exp.Boolean,
    exp.Null,
    exp.Neg,
    exp.Paren,
    exp.Cast,
    exp.DataType,
    exp.DataTypeParam,
    exp.Array,
    exp.Tuple,
)


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
        mapped = _operations(expression, span, raw)
        if not mapped and _is_unmapped_alter_table(expression):
            diagnostics.append(
                mg000.diagnostic(
                    span,
                    raw,
                    "This ALTER TABLE uses a form migrate-guard cannot map to a known "
                    "operation, so nothing in it was checked.",
                )
            )
        operations.extend(mapped)

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
    if isinstance(expression, exp.Command):
        return _command(expression, span, raw)
    if isinstance(expression, (exp.Insert, exp.Update, exp.Delete)):
        return _dml(expression, span, raw)
    if isinstance(expression, exp.TruncateTable):
        return [_other(span, raw, "TRUNCATE", _table(expression))]
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
    return [_other(span, raw, f"CREATE {kind}" if kind else "CREATE", None)]


def _drop(expression: exp.Drop, span: SourceSpan, raw: str) -> list[Operation]:
    kind = str(expression.args.get("kind") or "").upper()
    if kind == "TABLE":
        return [Operation(kind=OpKind.drop_table, span=span, raw=raw, table=_table(expression))]
    if kind == "TYPE":
        return [Operation(kind=OpKind.drop_type, span=span, raw=raw, table=_table(expression))]
    return [_other(span, raw, f"DROP {kind}" if kind else "DROP", None)]


def _dml(expression: exp.Expression, span: SourceSpan, raw: str) -> list[Operation]:
    verbs = {exp.Insert: "insert", exp.Update: "update", exp.Delete: "delete"}
    verb = verbs[type(expression)]
    return [
        Operation(
            kind=OpKind.dml,
            span=span,
            raw=raw,
            table=_table(expression),
            details={"verb": verb},
        )
    ]


def _is_unmapped_alter_table(expression: exp.Expression) -> bool:
    """True for an ALTER TABLE that sqlglot could only keep as a raw command tail.

    A multi-action ALTER lands here, and it can carry a DROP COLUMN, a type
    change, or a SET NOT NULL. Dropping it silently would report the file as
    clean, so the caller raises MG000 instead.
    """
    if not isinstance(expression, exp.Command):
        return False
    if str(expression.this or "").upper() != "ALTER":
        return False
    return ALTER_TABLE_TAIL.match(_command_tail(expression)) is not None


def _command_tail(expression: exp.Command) -> str:
    return " ".join(str(expression.args.get("expression") or "").split())


def _command(expression: exp.Command, span: SourceSpan, raw: str) -> list[Operation]:
    """Recover the two ALTER forms sqlglot does not model from the command tail."""
    if str(expression.this or "").upper() != "ALTER":
        return []
    tail = _command_tail(expression)

    match = VALIDATE_CONSTRAINT.match(tail)
    if match:
        return [
            Operation(
                kind=OpKind.validate_constraint,
                span=span,
                raw=raw,
                table=_identifier(match["table"]),
                details={"constraint": _identifier(match["name"])},
            )
        ]

    match = UNIQUE_USING_INDEX.match(tail)
    if match:
        return [
            Operation(
                kind=OpKind.add_unique_constraint,
                span=span,
                raw=raw,
                table=_identifier(match["table"]),
                details={"using_index": True},
            )
        ]
    return []


def _alter(expression: exp.Alter, span: SourceSpan, raw: str) -> list[Operation]:
    table = _table_of(expression.this)
    not_valid = bool(expression.args.get("not_valid"))
    operations: list[Operation] = []
    for action in expression.args.get("actions") or []:
        operations.extend(_action(action, span, raw, table, not_valid))
    return operations


def _action(
    action: exp.Expression,
    span: SourceSpan,
    raw: str,
    table: str | None,
    not_valid: bool,
) -> list[Operation]:
    if isinstance(action, exp.ColumnDef):
        return [_add_column(action, span, raw, table)]
    if isinstance(action, exp.AlterColumn):
        return [_alter_column(action, span, raw, table)]
    if isinstance(action, exp.ModifyColumn):
        return _modify_column(action, span, raw, table)
    if isinstance(action, exp.RenameColumn):
        return [
            Operation(
                kind=OpKind.rename_column,
                span=span,
                raw=raw,
                table=table,
                column=_name(action.this),
                details={"new_name": _name(action.args.get("to"))},
            )
        ]
    if isinstance(action, exp.AlterRename):
        return [
            Operation(
                kind=OpKind.rename_table,
                span=span,
                raw=raw,
                table=table,
                details={"new_name": _table_of(action.this)},
            )
        ]
    if isinstance(action, exp.AddConstraint):
        return _add_constraint(action, span, raw, table, not_valid)
    if isinstance(action, exp.Drop):
        kind = str(action.args.get("kind") or "").upper()
        if kind == "COLUMN":
            return [
                Operation(
                    kind=OpKind.drop_column,
                    span=span,
                    raw=raw,
                    table=table,
                    column=_name(action.this),
                )
            ]
        return [_other(span, raw, f"ALTER TABLE DROP {kind}".strip(), table)]
    return [_other(span, raw, "ALTER TABLE", table)]


def _add_column(action: exp.ColumnDef, span: SourceSpan, raw: str, table: str | None) -> Operation:
    default = _constraint_of(action, exp.DefaultColumnConstraint)
    return Operation(
        kind=OpKind.add_column,
        span=span,
        raw=raw,
        table=table,
        column=_name(action.this),
        details={
            "type": _type_name(action.args.get("kind")),
            "not_null": _is_not_null(action),
            "has_default": default is not None,
            "default_volatile": default is not None and _volatile(default.this),
        },
    )


def _alter_column(
    action: exp.AlterColumn, span: SourceSpan, raw: str, table: str | None
) -> Operation:
    column = _name(action.this)
    dtype = action.args.get("dtype")
    if dtype is not None:
        return Operation(
            kind=OpKind.alter_column_type,
            span=span,
            raw=raw,
            table=table,
            column=column,
            details={"new_type": _type_name(dtype), "old_type": None},
        )
    if action.args.get("allow_null") is False:
        return Operation(kind=OpKind.set_not_null, span=span, raw=raw, table=table, column=column)
    return _other(span, raw, "ALTER TABLE ALTER COLUMN", table)


def _modify_column(
    action: exp.ModifyColumn, span: SourceSpan, raw: str, table: str | None
) -> list[Operation]:
    """MySQL MODIFY/CHANGE: always a type change, plus a rename when CHANGE renames."""
    definition = action.this
    if not isinstance(definition, exp.ColumnDef):
        return [_other(span, raw, "ALTER TABLE MODIFY", table)]

    column = _name(definition.this)
    previous = _name(action.args.get("rename_from"))
    dtype = definition.args.get("kind")
    operations: list[Operation] = []

    if previous is not None and previous != column:
        operations.append(
            Operation(
                kind=OpKind.rename_column,
                span=span,
                raw=raw,
                table=table,
                column=previous,
                details={"new_name": column},
            )
        )

    if isinstance(dtype, exp.DataType) and dtype.this is exp.DataType.Type.ENUM:
        operations.append(
            Operation(kind=OpKind.redefine_enum, span=span, raw=raw, table=table, column=column)
        )
    else:
        operations.append(
            Operation(
                kind=OpKind.alter_column_type,
                span=span,
                raw=raw,
                table=table,
                column=column,
                details={"new_type": _type_name(dtype), "old_type": None},
            )
        )
    return operations


def _add_constraint(
    action: exp.AddConstraint,
    span: SourceSpan,
    raw: str,
    table: str | None,
    not_valid: bool,
) -> list[Operation]:
    operations: list[Operation] = []
    for entry in action.args.get("expressions") or []:
        name = _name(entry.this) if isinstance(entry, exp.Constraint) else None
        body = entry.expressions if isinstance(entry, exp.Constraint) else [entry]
        for node in body:
            operations.append(_constraint_operation(node, span, raw, table, name, not_valid))
    return operations


def _constraint_operation(
    node: exp.Expression,
    span: SourceSpan,
    raw: str,
    table: str | None,
    name: str | None,
    not_valid: bool,
) -> Operation:
    if isinstance(node, exp.ForeignKey):
        return Operation(
            kind=OpKind.add_foreign_key,
            span=span,
            raw=raw,
            table=table,
            details={"not_valid": not_valid},
        )
    if isinstance(node, exp.UniqueColumnConstraint):
        return Operation(
            kind=OpKind.add_unique_constraint,
            span=span,
            raw=raw,
            table=table,
            details={"using_index": False},
        )
    if isinstance(node, exp.CheckColumnConstraint) and not_valid:
        return Operation(
            kind=OpKind.add_check_not_valid,
            span=span,
            raw=raw,
            table=table,
            column=_not_null_column(node),
            details={"constraint": name},
        )
    return _other(span, raw, "ALTER TABLE ADD CONSTRAINT", table)


def _not_null_column(node: exp.CheckColumnConstraint) -> str | None:
    """The column of a CHECK (col IS NOT NULL) body, or None for any other check."""
    body = node.this
    if isinstance(body, exp.Paren):
        body = body.this
    if (
        isinstance(body, exp.Is)
        and body.args.get("negate")
        and isinstance(body.expression, exp.Null)
        and isinstance(body.this, exp.Column)
    ):
        return body.this.name or None
    return None


def _other(span: SourceSpan, raw: str, statement_type: str, table: str | None) -> Operation:
    return Operation(
        kind=OpKind.other_ddl,
        span=span,
        raw=raw,
        table=table,
        details={"statement_type": statement_type},
    )


def _is_not_null(definition: exp.ColumnDef) -> bool:
    constraint = _constraint_of(definition, exp.NotNullColumnConstraint)
    return constraint is not None and not constraint.args.get("allow_null")


def _constraint_of(definition: exp.ColumnDef, kind: type[exp.Expression]) -> exp.Expression | None:
    for constraint in definition.args.get("constraints") or []:
        if isinstance(constraint.kind, kind):
            return constraint.kind
    return None


def _volatile(default: exp.Expression | None) -> bool:
    if default is None:
        return False
    return not all(isinstance(node, CONSTANT_NODES) for node in default.walk())


def _type_name(dtype: exp.Expression | None) -> str | None:
    if dtype is None:
        return None
    return dtype.sql().lower() or None


def _table(expression: exp.Expression) -> str | None:
    table = expression.find(exp.Table)
    return table.name if table is not None else None


def _table_of(node: exp.Expression | None) -> str | None:
    if node is None:
        return None
    return node.name or None


def _identifier(text: str) -> str | None:
    """Last dotted part of a raw identifier, with quoting removed."""
    name = text.split(".")[-1].strip('"`')
    return name or None


def _name(node: exp.Expression | None) -> str | None:
    return node.name if node is not None and node.name else None
