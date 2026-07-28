from __future__ import annotations

from conftest import make_op

from migrate_guard.config import Config
from migrate_guard.ir import Finding, OpKind
from migrate_guard.rules import mg007, rules_for

RULE = mg007.RULE


def check(op: object, dialect: str = "postgres") -> Finding | None:
    return RULE.check(op, [op], 0, Config(dialect=dialect))


def unique_constraint(using_index: bool) -> object:
    return make_op(
        OpKind.add_unique_constraint,
        table="users",
        line=2,
        raw="ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email)",
        using_index=using_index,
    )


def test_the_rule_is_postgres_only() -> None:
    assert RULE.dialects == ("postgres",)
    assert RULE in rules_for("postgres")
    assert RULE not in rules_for("mysql")


def test_a_self_building_unique_constraint_fires() -> None:
    finding = check(unique_constraint(using_index=False))

    assert finding is not None
    assert finding.code == "MG007"
    assert finding.severity == "error"
    assert "ACCESS EXCLUSIVE" in finding.message
    assert "CREATE UNIQUE INDEX CONCURRENTLY" in finding.safe_alternative
    assert "USING INDEX" in finding.safe_alternative


def test_using_index_is_the_safe_form() -> None:
    assert check(unique_constraint(using_index=True)) is None


def test_other_operations_are_not_mg007() -> None:
    assert check(make_op(OpKind.create_index, table="users", unique=True, concurrent=False)) is None
