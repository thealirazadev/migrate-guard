from __future__ import annotations

import pytest

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
    text = "SET lock_timeout = '5s';\nSET LOCAL statement_timeout = 0;\n"
    result = sql.extract("db/x.sql", text, "postgres")

    assert result.operations == ()
    assert result.diagnostics == ()
    assert result.statement_count == 2


def test_mysql_backticks_parse_under_the_mysql_dialect() -> None:
    text = "DROP TABLE `audit_legacy`;\n"
    (op,) = sql.extract("db/x.sql", text, "mysql").operations

    assert op.kind is OpKind.drop_table
    assert op.table == "audit_legacy"


def one(statement: str, dialect: str = "postgres") -> object:
    (op,) = sql.extract("db/x.sql", f"{statement};\n", dialect).operations
    return op


def kinds(statement: str, dialect: str = "postgres") -> list[OpKind]:
    return [op.kind for op in sql.extract("db/x.sql", f"{statement};\n", dialect).operations]


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("ALTER TABLE users ADD COLUMN email text", OpKind.add_column),
        ("ALTER TABLE users ALTER COLUMN email TYPE text", OpKind.alter_column_type),
        ("ALTER TABLE users ALTER COLUMN email SET NOT NULL", OpKind.set_not_null),
        ("ALTER TABLE users RENAME COLUMN email TO primary_email", OpKind.rename_column),
        ("ALTER TABLE users RENAME TO people", OpKind.rename_table),
        ("ALTER TABLE users ADD CONSTRAINT k UNIQUE (email)", OpKind.add_unique_constraint),
        ("DROP TYPE order_status", OpKind.drop_type),
        ("INSERT INTO users (id) VALUES (1)", OpKind.dml),
        ("TRUNCATE TABLE users", OpKind.other_ddl),
        ("ALTER TABLE users DROP CONSTRAINT k", OpKind.other_ddl),
        ("ALTER TABLE users ALTER COLUMN email SET DEFAULT 'x'", OpKind.other_ddl),
    ],
)
def test_postgres_statements_map_to_their_kind(statement: str, expected: OpKind) -> None:
    assert one(statement).kind is expected


def test_add_column_records_nullability_and_default_shape() -> None:
    plain = one("ALTER TABLE users ADD COLUMN email text")
    enforced = one("ALTER TABLE users ADD COLUMN email text NOT NULL")
    constant = one("ALTER TABLE users ADD COLUMN email text NOT NULL DEFAULT ''")
    volatile = one("ALTER TABLE users ADD COLUMN c timestamptz DEFAULT now()")

    assert plain.details == {
        "type": "text",
        "not_null": False,
        "has_default": False,
        "default_volatile": False,
    }
    assert enforced.details["not_null"] is True
    assert constant.details == {
        "type": "text",
        "not_null": True,
        "has_default": True,
        "default_volatile": False,
    }
    assert volatile.details["default_volatile"] is True


@pytest.mark.parametrize(
    ("default", "volatile"),
    [
        ("5", False),
        ("-1", False),
        ("''", False),
        ("'{}'::jsonb", False),
        ("true", False),
        ("now()", True),
        ("CURRENT_TIMESTAMP", True),
        ("gen_random_uuid()", True),
        ("random()", True),
        ("(SELECT 1)", True),
    ],
)
def test_only_constant_defaults_count_as_non_volatile(default: str, volatile: bool) -> None:
    op = one(f"ALTER TABLE users ADD COLUMN x text DEFAULT {default}")

    assert op.details["default_volatile"] is volatile


def test_type_changes_record_the_new_type_and_an_unknown_old_one() -> None:
    op = one("ALTER TABLE users ALTER COLUMN email TYPE varchar(255)")

    assert op.details == {"new_type": "varchar(255)", "old_type": None}
    assert op.column == "email"


def test_renames_carry_the_new_name() -> None:
    column = one("ALTER TABLE users RENAME COLUMN email TO primary_email")
    table = one("ALTER TABLE users RENAME TO people")

    assert column.column == "email"
    assert column.details == {"new_name": "primary_email"}
    assert table.details == {"new_name": "people"}


def test_a_not_null_check_records_its_column_and_constraint() -> None:
    op = one("ALTER TABLE users ADD CONSTRAINT users_email_nn CHECK (email IS NOT NULL) NOT VALID")

    assert op.kind is OpKind.add_check_not_valid
    assert op.column == "email"
    assert op.details == {"constraint": "users_email_nn"}


def test_a_check_that_is_not_a_null_test_has_no_column() -> None:
    op = one("ALTER TABLE users ADD CONSTRAINT ck CHECK (age > 0) NOT VALID")

    assert op.kind is OpKind.add_check_not_valid
    assert op.column is None


def test_a_valid_check_is_not_the_not_valid_form() -> None:
    assert one("ALTER TABLE users ADD CONSTRAINT ck CHECK (age > 0)").kind is OpKind.other_ddl


@pytest.mark.parametrize("statement", ["ALTER TABLE users VALIDATE CONSTRAINT users_email_nn"])
def test_validate_constraint_survives_the_command_fallback(statement: str) -> None:
    op = one(statement)

    assert op.kind is OpKind.validate_constraint
    assert op.table == "users"
    assert op.details == {"constraint": "users_email_nn"}


def test_validate_constraint_handles_only_and_a_qualified_name() -> None:
    op = one("ALTER TABLE ONLY public.users VALIDATE CONSTRAINT users_email_nn")

    assert op.table == "users"
    assert op.details == {"constraint": "users_email_nn"}


def test_unique_using_index_survives_the_command_fallback() -> None:
    op = one("ALTER TABLE users ADD CONSTRAINT k UNIQUE USING INDEX users_email_key")

    assert op.kind is OpKind.add_unique_constraint
    assert op.details == {"using_index": True}


def test_a_plain_unique_constraint_is_not_using_an_index() -> None:
    assert one("ALTER TABLE users ADD CONSTRAINT k UNIQUE (email)").details == {
        "using_index": False
    }


def test_other_alter_commands_are_still_ignored() -> None:
    assert sql.extract("db/x.sql", "ALTER TYPE s ADD VALUE 'x';\n", "postgres").operations == ()


def test_foreign_keys_record_their_validation_mode() -> None:
    eager = one("ALTER TABLE orders ADD CONSTRAINT f FOREIGN KEY (u) REFERENCES users (id)")
    deferred = one(
        "ALTER TABLE orders ADD CONSTRAINT f FOREIGN KEY (u) REFERENCES users (id) NOT VALID"
    )

    assert eager.table == "orders"
    assert eager.details == {"not_valid": False}
    assert deferred.details == {"not_valid": True}


@pytest.mark.parametrize(
    ("statement", "verb"),
    [
        ("INSERT INTO users (id) VALUES (1)", "insert"),
        ("UPDATE users SET email = 'x'", "update"),
        ("DELETE FROM users WHERE id = 1", "delete"),
    ],
)
def test_dml_records_its_verb(statement: str, verb: str) -> None:
    op = one(statement)

    assert op.kind is OpKind.dml
    assert op.table == "users"
    assert op.details == {"verb": verb}


def test_mysql_modify_is_a_type_change() -> None:
    op = one("ALTER TABLE users MODIFY email varchar(255) NOT NULL", "mysql")

    assert op.kind is OpKind.alter_column_type
    assert op.details == {"new_type": "varchar(255)", "old_type": None}


def test_mysql_change_with_a_new_name_is_a_rename_and_a_type_change() -> None:
    operations = sql.extract(
        "db/x.sql", "ALTER TABLE users CHANGE email primary_email varchar(255);\n", "mysql"
    ).operations

    assert [op.kind for op in operations] == [OpKind.rename_column, OpKind.alter_column_type]
    assert operations[0].details == {"new_name": "primary_email"}


def test_mysql_change_keeping_the_name_is_only_a_type_change() -> None:
    assert kinds("ALTER TABLE users CHANGE COLUMN email email varchar(255)", "mysql") == [
        OpKind.alter_column_type
    ]


def test_mysql_enum_redefinition_has_its_own_kind() -> None:
    op = one("ALTER TABLE orders MODIFY status ENUM('new', 'paid')", "mysql")

    assert op.kind is OpKind.redefine_enum
    assert op.column == "status"


def test_mysql_add_unique_key_is_a_unique_constraint() -> None:
    op = one("ALTER TABLE users ADD UNIQUE KEY users_email_key (email)", "mysql")

    assert op.kind is OpKind.add_unique_constraint
    assert op.details == {"using_index": False}
