from __future__ import annotations

import pytest
from conftest import make_op

from migrate_guard.config import Config
from migrate_guard.ir import OpKind
from migrate_guard.rules import mg004, rules_for

RULE = mg004.RULE


def check(op: object, dialect: str = "postgres") -> object:
    return RULE.check(op, [op], 0, Config(dialect=dialect))


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
def test_drop_table_fires_on_both_dialects(dialect: str) -> None:
    op = make_op(OpKind.drop_table, table="audit_legacy", line=3, raw="DROP TABLE audit_legacy")
    finding = check(op, dialect)

    assert finding.code == "MG004"
    assert finding.severity == "error"
    assert finding.message == "DROP TABLE removes audit_legacy and its data permanently."
    assert "later migration" in finding.safe_alternative


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
def test_drop_column_fires_on_both_dialects(dialect: str) -> None:
    op = make_op(
        OpKind.drop_column,
        table="users",
        column="legacy_flag",
        raw="ALTER TABLE users DROP COLUMN legacy_flag",
    )
    finding = check(op, dialect)

    assert finding.code == "MG004"
    assert "legacy_flag" in finding.message
    assert "users" in finding.message


def test_other_operations_are_not_mg004() -> None:
    op = make_op(OpKind.create_index, table="users", unique=False, concurrent=False)

    assert check(op) is None


def test_the_rule_applies_to_both_dialects() -> None:
    assert RULE in rules_for("postgres")
    assert RULE in rules_for("mysql")
