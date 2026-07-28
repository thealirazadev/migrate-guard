from __future__ import annotations

from conftest import make_op

from migrate_guard.config import Config
from migrate_guard.ir import OpKind
from migrate_guard.rules import mg002, rules_for

POSTGRES = Config(dialect="postgres")
RULE = mg002.RULE


def check(op: object) -> object:
    return RULE.check(op, [op], 0, POSTGRES)


def test_plain_create_index_fires() -> None:
    op = make_op(
        OpKind.create_index,
        table="users",
        line=7,
        raw="CREATE INDEX users_email_idx ON users (email)",
        unique=False,
        concurrent=False,
    )
    finding = check(op)

    assert finding.code == "MG002"
    assert finding.severity == "error"
    assert finding.span.line == 7
    assert finding.table == "users"
    assert "blocks all writes to users" in finding.message
    assert finding.safe_alternative == (
        "CREATE INDEX CONCURRENTLY users_email_idx ON users (email); "
        "run it outside a transaction."
    )


def test_concurrent_create_index_is_silent() -> None:
    op = make_op(
        OpKind.create_index,
        table="users",
        raw="CREATE INDEX CONCURRENTLY users_email_idx ON users (email)",
        unique=False,
        concurrent=True,
    )

    assert check(op) is None


def test_unique_index_keeps_its_keyword_in_the_fix() -> None:
    op = make_op(
        OpKind.create_index,
        table="users",
        raw="CREATE UNIQUE INDEX users_email_key ON users (email)",
        unique=True,
        concurrent=False,
    )

    assert check(op).safe_alternative.startswith("CREATE UNIQUE INDEX CONCURRENTLY")


def test_non_sql_raw_falls_back_to_a_generic_fix() -> None:
    op = make_op(
        OpKind.create_index,
        table="users",
        raw="$table->index('email')",
        unique=False,
        concurrent=False,
    )

    assert check(op).safe_alternative.startswith("Build the index with CREATE INDEX CONCURRENTLY")


def test_other_operations_are_not_mg002() -> None:
    assert check(make_op(OpKind.drop_table, table="users")) is None


def test_the_rule_is_postgres_only() -> None:
    assert RULE.dialects == ("postgres",)
    assert RULE in rules_for("postgres")
    assert RULE not in rules_for("mysql")
