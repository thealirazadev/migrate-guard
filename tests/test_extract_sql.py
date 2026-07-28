from __future__ import annotations

from migrate_guard.extractors import sql
from migrate_guard.ir import OpKind

MULTI = """-- header comment
CREATE TABLE fresh (
    id bigserial PRIMARY KEY
);

CREATE INDEX users_email_idx ON users (email);

DROP TABLE audit_legacy;

ALTER TABLE users DROP COLUMN legacy_flag;
"""


def test_line_numbers_survive_multi_statement_files() -> None:
    result = sql.extract("db/x.sql", MULTI, "postgres")

    assert [(op.kind, op.span.line) for op in result.operations] == [
        (OpKind.create_table, 2),
        (OpKind.create_index, 6),
        (OpKind.drop_table, 8),
        (OpKind.drop_column, 10),
    ]
    assert result.statement_count == 4
    assert result.diagnostics == ()


def test_operation_details_and_names() -> None:
    result = sql.extract("db/x.sql", MULTI, "postgres")
    index_op, drop_table_op, drop_column_op = result.operations[1:]

    assert index_op.table == "users"
    assert index_op.details == {"unique": False, "concurrent": False}
    assert drop_table_op.table == "audit_legacy"
    assert drop_column_op.table == "users"
    assert drop_column_op.column == "legacy_flag"


def test_concurrent_and_unique_indexes_are_flagged_in_details() -> None:
    text = "CREATE UNIQUE INDEX CONCURRENTLY users_email_key ON users (email);\n"
    (op,) = sql.extract("db/x.sql", text, "postgres").operations

    assert op.details == {"unique": True, "concurrent": True}


def test_quoted_and_qualified_identifiers_are_normalized() -> None:
    text = 'DROP TABLE public."Audit_Legacy";\n'
    (op,) = sql.extract("db/x.sql", text, "postgres").operations

    assert op.table == "Audit_Legacy"


def test_one_alter_can_produce_several_operations() -> None:
    text = "ALTER TABLE users DROP COLUMN a, DROP COLUMN b;\n"
    operations = sql.extract("db/x.sql", text, "postgres").operations

    assert [op.column for op in operations] == ["a", "b"]
    assert all(op.kind is OpKind.drop_column for op in operations)


def test_unparseable_statement_becomes_mg000_and_the_file_continues() -> None:
    text = "CREATE INDEX i ON users (email);\n\nTHIS IS NOT SQL AT ALL;\n\nDROP TABLE old;\n"
    result = sql.extract("db/x.sql", text, "postgres")

    assert [op.kind for op in result.operations] == [OpKind.create_index, OpKind.drop_table]
    (diagnostic,) = result.diagnostics
    assert diagnostic.code == "MG000"
    assert diagnostic.severity == "warning"
    assert diagnostic.span.line == 3
    assert diagnostic.statement == "THIS IS NOT SQL AT ALL"
    assert result.statement_count == 3


def test_untokenizable_file_reports_one_diagnostic() -> None:
    result = sql.extract("db/x.sql", "%%$$@@\n", "postgres")

    assert result.operations == ()
    (diagnostic,) = result.diagnostics
    assert diagnostic.code == "MG000"
    assert diagnostic.span.line == 1
    assert "could not be tokenized" in diagnostic.message


def test_statement_excerpt_is_one_line_and_capped() -> None:
    columns = ", ".join(f"column_{n} text" for n in range(60))
    (op,) = sql.extract("db/x.sql", f"CREATE TABLE wide (\n{columns}\n);\n", "postgres").operations

    assert "\n" not in op.raw
    assert len(op.raw) == 200


def test_unmodelled_statements_produce_nothing() -> None:
    text = "SET lock_timeout = '5s';\nINSERT INTO users (id) VALUES (1);\n"
    result = sql.extract("db/x.sql", text, "postgres")

    assert result.operations == ()
    assert result.diagnostics == ()
    assert result.statement_count == 2


def test_mysql_backticks_parse_under_the_mysql_dialect() -> None:
    text = "DROP TABLE `audit_legacy`;\n"
    (op,) = sql.extract("db/x.sql", text, "mysql").operations

    assert op.kind is OpKind.drop_table
    assert op.table == "audit_legacy"
