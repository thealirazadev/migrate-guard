from __future__ import annotations

from conftest import make_op

from migrate_guard.config import Config
from migrate_guard.ir import Finding, OpKind
from migrate_guard.rules import mg008, rules_for

RULE = mg008.RULE


def check(op: object, dialect: str) -> Finding | None:
    return RULE.check(op, [op], 0, Config(dialect=dialect))


def enum_redefinition() -> object:
    return make_op(
        OpKind.redefine_enum,
        table="orders",
        column="status",
        line=2,
        raw="ALTER TABLE orders MODIFY status ENUM('new', 'paid')",
    )


def dropped_type() -> object:
    return make_op(OpKind.drop_type, table="order_status", line=2, raw="DROP TYPE order_status")


def test_the_rule_applies_to_both_dialects() -> None:
    assert RULE in rules_for("postgres")
    assert RULE in rules_for("mysql")


def test_a_mysql_enum_redefinition_is_a_warning() -> None:
    finding = check(enum_redefinition(), "mysql")

    assert finding is not None
    assert finding.code == "MG008"
    assert finding.severity == "warning"
    assert "cannot see the previous one" in finding.message
    assert "Confirm against the previous schema" in finding.safe_alternative


def test_a_postgres_drop_type_is_a_warning() -> None:
    finding = check(dropped_type(), "postgres")

    assert finding is not None
    assert finding.severity == "warning"
    assert "DROP TYPE order_status" in finding.message
    assert "ALTER TYPE ... ADD VALUE" in finding.safe_alternative


def test_each_heuristic_belongs_to_its_own_dialect() -> None:
    assert check(enum_redefinition(), "postgres") is None
    assert check(dropped_type(), "mysql") is None


def test_other_operations_are_not_mg008() -> None:
    assert check(make_op(OpKind.drop_table, table="orders"), "postgres") is None
    assert (
        check(make_op(OpKind.alter_column_type, table="orders", column="status"), "mysql") is None
    )
