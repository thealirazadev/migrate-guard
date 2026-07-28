from __future__ import annotations

import pytest
from conftest import make_op

from migrate_guard.config import Config
from migrate_guard.ir import Finding, OpKind
from migrate_guard.rules import mg005, rules_for

RULE = mg005.RULE
DIALECTS = ("postgres", "mysql")


def check(op: object, dialect: str = "postgres") -> Finding | None:
    return RULE.check(op, [op], 0, Config(dialect=dialect))


def test_the_rule_applies_to_both_dialects() -> None:
    assert RULE in rules_for("postgres")
    assert RULE in rules_for("mysql")


@pytest.mark.parametrize("dialect", DIALECTS)
def test_renaming_a_column_fires(dialect: str) -> None:
    op = make_op(
        OpKind.rename_column,
        table="users",
        column="email",
        line=2,
        raw="ALTER TABLE users RENAME COLUMN email TO primary_email",
        new_name="primary_email",
    )
    finding = check(op, dialect)

    assert finding is not None
    assert finding.code == "MG005"
    assert finding.severity == "error"
    assert finding.message == (
        "Renaming users.email to primary_email removes the old name while the previous "
        "release is still selecting it."
    )
    assert "MG004 allow" in finding.safe_alternative


@pytest.mark.parametrize("dialect", DIALECTS)
def test_renaming_a_table_fires(dialect: str) -> None:
    op = make_op(
        OpKind.rename_table,
        table="orders",
        line=4,
        raw="ALTER TABLE orders RENAME TO purchases",
        new_name="purchases",
    )
    finding = check(op, dialect)

    assert finding is not None
    assert finding.span.line == 4
    assert "Renaming orders to purchases" in finding.message
    assert "dual-write" in finding.safe_alternative


def test_a_rename_with_no_recorded_target_still_reports() -> None:
    op = make_op(OpKind.rename_table, table="orders", raw="Schema::rename(...)")

    assert check(op) is not None


def test_other_operations_are_not_mg005() -> None:
    assert check(make_op(OpKind.drop_column, table="users", column="email")) is None
    assert check(make_op(OpKind.alter_column_type, table="users", column="email")) is None
