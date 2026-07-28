from __future__ import annotations

from conftest import make_op

from migrate_guard.config import Config
from migrate_guard.ir import Finding, OpKind
from migrate_guard.rules import mg006, rules_for

RULE = mg006.RULE


def check(op: object, dialect: str = "postgres") -> Finding | None:
    return RULE.check(op, [op], 0, Config(dialect=dialect))


def foreign_key(not_valid: bool) -> object:
    return make_op(
        OpKind.add_foreign_key,
        table="orders",
        line=2,
        raw="ALTER TABLE orders ADD CONSTRAINT orders_user_fk FOREIGN KEY (user_id) "
        "REFERENCES users (id)",
        not_valid=not_valid,
    )


def test_the_rule_is_postgres_only() -> None:
    assert RULE.dialects == ("postgres",)
    assert RULE in rules_for("postgres")
    assert RULE not in rules_for("mysql")


def test_an_eagerly_validated_foreign_key_fires() -> None:
    finding = check(foreign_key(not_valid=False))

    assert finding is not None
    assert finding.code == "MG006"
    assert finding.severity == "error"
    assert finding.table == "orders"
    assert "without NOT VALID" in finding.message
    assert "VALIDATE CONSTRAINT" in finding.safe_alternative


def test_not_valid_is_the_safe_form() -> None:
    assert check(foreign_key(not_valid=True)) is None


def test_validate_constraint_alone_is_never_a_finding() -> None:
    op = make_op(
        OpKind.validate_constraint,
        table="orders",
        raw="ALTER TABLE orders VALIDATE CONSTRAINT orders_user_fk",
        constraint="orders_user_fk",
    )

    assert check(op) is None


def test_other_operations_are_not_mg006() -> None:
    assert check(make_op(OpKind.add_unique_constraint, table="users", using_index=False)) is None
