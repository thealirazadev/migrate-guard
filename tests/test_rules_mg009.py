from __future__ import annotations

from conftest import make_op

from migrate_guard.config import Config
from migrate_guard.ir import Finding, OpKind
from migrate_guard.rules import mg009, rules_for

RULE = mg009.RULE


def check(file_ops: list[object], index: int, dialect: str = "mysql") -> Finding | None:
    return RULE.check(file_ops[index], file_ops, index, Config(dialect=dialect))


def mixed_file() -> list[object]:
    return [
        make_op(OpKind.add_column, table="users", column="nickname", line=2),
        make_op(
            OpKind.dml,
            table="users",
            line=4,
            raw="UPDATE users SET nickname = 'unset'",
            verb="update",
        ),
        make_op(OpKind.dml, table="users", line=6, raw="DELETE FROM users", verb="delete"),
    ]


def test_the_rule_is_mysql_only() -> None:
    assert RULE.dialects == ("mysql",)
    assert RULE in rules_for("mysql")
    assert RULE not in rules_for("postgres")


def test_a_mixed_file_fires_once_at_the_first_data_statement() -> None:
    file_ops = mixed_file()
    finding = check(file_ops, 1)

    assert finding is not None
    assert finding.code == "MG009"
    assert finding.severity == "warning"
    assert finding.span.line == 4
    assert "(UPDATE)" in finding.message
    assert check(file_ops, 2) is None


def test_a_schema_only_file_is_silent() -> None:
    file_ops = [make_op(OpKind.add_column, table="users", column="nickname")]

    assert check(file_ops, 0) is None


def test_a_data_only_file_is_silent() -> None:
    file_ops = [
        make_op(OpKind.dml, table="users", line=1, verb="update"),
        make_op(OpKind.dml, table="users", line=3, verb="delete"),
    ]

    assert check(file_ops, 0) is None
    assert check(file_ops, 1) is None


def test_data_before_schema_still_counts_as_mixed() -> None:
    file_ops = [
        make_op(OpKind.dml, table="users", line=1, verb="insert"),
        make_op(OpKind.create_index, table="users", line=3, unique=False, concurrent=False),
    ]

    assert check(file_ops, 0) is not None


def test_recognized_but_unmodelled_ddl_counts_as_schema() -> None:
    file_ops = [
        make_op(OpKind.other_ddl, table="users", line=1, statement_type="TRUNCATE"),
        make_op(OpKind.dml, table="users", line=3, verb="insert"),
    ]

    assert check(file_ops, 1) is not None
