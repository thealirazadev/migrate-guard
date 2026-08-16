"""Django migration extraction via ast.parse.

The Django extractor parses the migration file as Python AST, locates the
Migration class and its operations list, then maps each operation to the
shared IR. RunSQL statements are routed to the SQL extractor; RunPython
operations are ignored by design (they execute arbitrary Python and
cannot be statically analyzed for database risks).

Non-migration Python files are reported as MG000.
"""

from __future__ import annotations

import ast
from typing import Any

from ..ir import Allow, Finding, Operation, OpKind, SourceSpan, excerpt
from ..rules import mg000
from . import ExtractionResult
from .sql import extract as extract_sql


def extract(path: str, text: str, dialect: str) -> ExtractionResult:
    """Map one Django migration file to operations plus MG000 diagnostics."""
    # Parse the Python file
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        span = SourceSpan(file=path, line=exc.lineno or 1)
        return ExtractionResult(
            diagnostics=(
                mg000.diagnostic(
                    span,
                    excerpt(text),
                    f"{path} is not valid Python, so no operation in it was checked.",
                ),
            )
        )
    except Exception as exc:
        span = SourceSpan(file=path, line=1)
        return ExtractionResult(
            diagnostics=(
                mg000.diagnostic(
                    span,
                    excerpt(text),
                    f"{path} could not be parsed as Python, so no operation in it was checked.",
                ),
            )
        )

    # Find the Migration class and its operations
    migration_class = _find_migration_class(tree)
    if migration_class is None:
        span = SourceSpan(file=path, line=1)
        return ExtractionResult(
            diagnostics=(
                mg000.diagnostic(
                    span,
                    excerpt(text),
                    f"{path} does not define a Migration class, so it is not a Django "
                    "migration file.",
                ),
            )
        )

    operations_list = _find_operations_list(migration_class, text)
    if operations_list is None:
        span = SourceSpan(file=path, line=1)
        return ExtractionResult(
            diagnostics=(
                mg000.diagnostic(
                    span,
                    excerpt(text),
                    f"{path} Migration class does not define an operations list, so no "
                    "operation in it was checked.",
                ),
            )
        )

    # Extract operations
    operations: list[Operation] = []
    diagnostics: list[Finding] = []

    for op_node in operations_list:
        if not isinstance(op_node, ast.Call):
            continue

        span = SourceSpan(file=path, line=op_node.lineno or 1)
        raw = _get_operation_raw(text, op_node)

        # Get the operation class name
        op_class = _get_call_name(op_node.func)
        if op_class is None:
            continue

        # Map known operations
        if op_class == "CreateModel":
            operations.append(
                Operation(kind=OpKind.create_table, span=span, raw=raw)
            )
        elif op_class == "DeleteModel":
            operations.append(
                Operation(kind=OpKind.drop_table, span=span, raw=raw)
            )
        elif op_class == "RenameModel":
            operations.append(
                Operation(kind=OpKind.rename_table, span=span, raw=raw)
            )
        elif op_class == "AddField":
            details = _extract_add_field(op_node)
            operations.append(
                Operation(
                    kind=OpKind.add_column,
                    span=span,
                    raw=raw,
                    details=details,
                )
            )
        elif op_class == "RemoveField":
            operations.append(
                Operation(kind=OpKind.drop_column, span=span, raw=raw)
            )
        elif op_class == "RenameField":
            operations.append(
                Operation(kind=OpKind.rename_column, span=span, raw=raw)
            )
        elif op_class == "AlterField":
            operations.append(
                Operation(kind=OpKind.alter_column_type, span=span, raw=raw,
                          details={"old_type": None, "new_type": None})
            )
        elif op_class == "AddIndex":
            operations.append(
                Operation(kind=OpKind.create_index, span=span, raw=raw,
                          details={"unique": False, "concurrent": False})
            )
        elif op_class == "AddIndexConcurrently":
            atomic = _get_atomic_setting(migration_class, text)
            operations.append(
                Operation(
                    kind=OpKind.create_index,
                    span=span,
                    raw=raw,
                    details={"unique": False, "concurrent": atomic is False},
                )
            )
        elif op_class == "AddConstraint":
            operations.append(
                Operation(kind=OpKind.add_unique_constraint, span=span, raw=raw,
                          details={"using_index": False})
            )
        elif op_class == "AlterUniqueTogether":
            operations.append(
                Operation(kind=OpKind.add_unique_constraint, span=span, raw=raw,
                          details={"using_index": False})
            )
        elif op_class == "RunSQL":
            # Extract the SQL literal and route through SQL extractor
            sql_literal = _extract_runsql_literal(op_node)
            if sql_literal is None:
                diagnostics.append(
                    mg000.diagnostic(
                        span,
                        raw,
                        "RunSQL has a variable or complex argument; "
                        "migrate-guard could not analyze it.",
                    )
                )
            else:
                result = extract_sql(path, sql_literal, dialect)
                operations.extend(result.operations)
                diagnostics.extend(result.diagnostics)
        # RunPython is ignored by design

    return ExtractionResult(
        operations=tuple(operations),
        diagnostics=tuple(diagnostics),
        statement_count=len(operations),
    )


def _find_migration_class(tree: ast.Module) -> ast.ClassDef | None:
    """Find the Migration class in the module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Migration":
            return node
    return None


def _find_operations_list(
    migration_class: ast.ClassDef, text: str
) -> list[ast.expr] | None:
    """Find the operations list assignment in the Migration class."""
    for node in migration_class.body:
        if isinstance(node, ast.Assign):
            # Check if this is assigning to 'operations'
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "operations":
                    if isinstance(node.value, ast.List):
                        return node.value.elts
    return None


def _get_call_name(func: ast.expr) -> str | None:
    """Get the name of a function being called."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _extract_add_field(op_node: ast.Call) -> dict[str, Any]:
    """Extract details from an AddField operation."""
    details: dict[str, Any] = {
        "type": None,
        "not_null": False,
        "has_default": False,
        "default_volatile": False,
    }

    for keyword in op_node.keywords:
        if keyword.arg == "field":
            # Extract field type and constraints
            if isinstance(keyword.value, ast.Call):
                field_class = _get_call_name(keyword.value.func)
                details["type"] = field_class or None

                # Check for null=False (not null)
                for field_kw in keyword.value.keywords:
                    if field_kw.arg == "null":
                        if isinstance(field_kw.value, ast.Constant):
                            details["not_null"] = field_kw.value.value is False

                    # Check for default
                    if field_kw.arg == "default":
                        details["has_default"] = True
                        details["default_volatile"] = _is_volatile_default(field_kw.value)

    return details


def _is_volatile_default(node: ast.expr) -> bool:
    """Check if a default value is volatile (contains function calls)."""
    if isinstance(node, ast.Call):
        return True
    if isinstance(node, ast.Subscript):
        return True
    # Anything else is treated as constant
    return False


def _extract_runsql_literal(op_node: ast.Call) -> str | None:
    """Extract SQL literal from a RunSQL operation."""
    # RunSQL(sql, ...) - first positional argument is the SQL
    if op_node.args:
        first_arg = op_node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            return first_arg.value
    return None


def _get_atomic_setting(migration_class: ast.ClassDef, text: str) -> bool | None:
    """Check if the migration sets atomic = False."""
    for node in migration_class.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "atomic":
                    if isinstance(node.value, ast.Constant):
                        return node.value.value
    return None


def _get_operation_raw(text: str, op_node: ast.Call) -> str:
    """Extract raw text for an operation node."""
    try:
        if op_node.lineno is not None:
            lines = text.split("\n")
            if op_node.lineno <= len(lines):
                return excerpt(lines[op_node.lineno - 1])
    except Exception:
        pass
    return excerpt(text)
