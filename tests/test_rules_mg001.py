from __future__ import annotations

import pytest
from conftest import make_op

from migrate_guard.config import Config
from migrate_guard.ir import Finding, OpKind
from migrate_guard.rules import mg001, rules_for

RULE = mg001.RULE
VERSIONS = (10, 11, 12, 16)


def check(
    op: object,
    dialect: str = "postgres",
    version: int = 16,
    file_ops: list[object] | None = None,
    index: int = 0,
) -> Finding | None:
    operations = file_ops if file_ops is not None else [op]
    return RULE.check(op, operations, index, Config(dialect=dialect, postgres_version=version))


def type_change(old: str | None = None, new: str = "text", **overrides: object) -> object:
    return make_op(
        OpKind.alter_column_type,
        table="users",
        column="email",
        line=2,
        raw=f"ALTER TABLE users ALTER COLUMN email TYPE {new}",
        new_type=new,
        old_type=old,
        **overrides,
    )


def added_column(**details: object) -> object:
    return make_op(
        OpKind.add_column,
        table="users",
        column="status",
        line=2,
        raw="ALTER TABLE users ADD COLUMN status text",
        type="text",
        **details,
    )


def test_the_rule_applies_to_both_dialects() -> None:
    assert RULE in rules_for("postgres")
    assert RULE in rules_for("mysql")


# MG001(a) - type changes


@pytest.mark.parametrize("version", VERSIONS)
def test_type_change_fires_on_every_postgres_version(version: int) -> None:
    finding = check(type_change(), version=version)

    assert finding is not None
    assert finding.code == "MG001"
    assert finding.severity == "error"
    assert "ACCESS EXCLUSIVE" in finding.message
    assert finding.span.line == 2


def test_type_change_fires_on_mysql_with_the_copy_message() -> None:
    finding = check(type_change(new="varchar(255)"), dialect="mysql")

    assert finding is not None
    assert "copies the whole table" in finding.message


def test_unknown_old_type_is_treated_as_a_rewrite() -> None:
    assert check(type_change(old=None, new="varchar(500)")) is not None


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("varchar(50)", "varchar(255)"),
        ("varchar(50)", "text"),
        ("character varying(50)", "character varying(120)"),
        ("numeric(10,2)", "numeric(14,2)"),
        ("varbit(8)", "varbit(16)"),
    ],
)
def test_documented_postgres_widenings_stay_silent(old: str, new: str) -> None:
    assert check(type_change(old=old, new=new)) is None


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("varchar(255)", "varchar(50)"),
        ("text", "varchar(255)"),
        ("numeric(10,2)", "numeric(14,4)"),
        ("numeric(14,2)", "numeric(10,2)"),
        ("integer", "bigint"),
    ],
)
def test_narrowings_and_other_changes_still_fire(old: str, new: str) -> None:
    assert check(type_change(old=old, new=new)) is not None


def test_mysql_varchar_widening_is_safe_inside_one_length_class() -> None:
    assert check(type_change(old="varchar(20)", new="varchar(60)"), dialect="mysql") is None


def test_mysql_varchar_widening_across_the_length_class_still_fires() -> None:
    assert check(type_change(old="varchar(20)", new="varchar(200)"), dialect="mysql") is not None


def test_mysql_does_not_get_the_postgres_widenings() -> None:
    assert check(type_change(old="varchar(50)", new="text"), dialect="mysql") is not None


# MG001(b) - ADD COLUMN with a default


@pytest.mark.parametrize("version", [11, 12, 16])
def test_constant_default_is_metadata_only_from_eleven(version: int) -> None:
    op = added_column(not_null=True, has_default=True, default_volatile=False)

    assert check(op, version=version) is None


def test_constant_default_rewrites_before_eleven() -> None:
    op = added_column(not_null=True, has_default=True, default_volatile=False)
    finding = check(op, version=10)

    assert finding is not None
    assert "PostgreSQL 10" in finding.message


@pytest.mark.parametrize("version", VERSIONS)
def test_volatile_default_rewrites_on_every_version(version: int) -> None:
    op = added_column(not_null=False, has_default=True, default_volatile=True)

    assert check(op, version=version) is not None


@pytest.mark.parametrize("version", VERSIONS)
def test_a_column_without_a_default_is_never_mg001(version: int) -> None:
    op = added_column(not_null=True, has_default=False, default_volatile=False)

    assert check(op, version=version) is None


def test_mysql_never_gets_the_add_column_branch() -> None:
    op = added_column(not_null=True, has_default=True, default_volatile=True)

    assert check(op, dialect="mysql", version=10) is None


# MG001(c) - SET NOT NULL


@pytest.mark.parametrize("version", VERSIONS)
def test_a_bare_set_not_null_always_fires(version: int) -> None:
    op = make_op(OpKind.set_not_null, table="users", column="email", line=2)
    finding = check(op, version=version)

    assert finding is not None
    assert "scans every row" in finding.message


def not_null_sequence() -> list[object]:
    return [
        make_op(
            OpKind.add_check_not_valid,
            table="users",
            column="email",
            line=1,
            constraint="users_email_nn",
        ),
        make_op(
            OpKind.validate_constraint,
            table="users",
            line=2,
            constraint="users_email_nn",
        ),
        make_op(OpKind.set_not_null, table="users", column="email", line=3),
    ]


@pytest.mark.parametrize("version", [12, 16])
def test_the_validated_check_sequence_is_exempt_from_twelve(version: int) -> None:
    file_ops = not_null_sequence()

    assert check(file_ops[2], version=version, file_ops=file_ops, index=2) is None


@pytest.mark.parametrize("version", [10, 11])
def test_the_sequence_does_not_help_before_twelve(version: int) -> None:
    file_ops = not_null_sequence()

    assert check(file_ops[2], version=version, file_ops=file_ops, index=2) is not None


def test_an_unvalidated_check_does_not_suppress() -> None:
    file_ops = not_null_sequence()
    del file_ops[1]

    assert check(file_ops[1], file_ops=file_ops, index=1) is not None


def test_the_suppression_is_per_column() -> None:
    file_ops = [*not_null_sequence(), make_op(OpKind.set_not_null, table="users", column="phone")]

    assert check(file_ops[2], file_ops=file_ops, index=2) is None
    assert check(file_ops[3], file_ops=file_ops, index=3) is not None


def test_a_check_on_another_table_does_not_suppress() -> None:
    file_ops = not_null_sequence()
    file_ops[0] = make_op(
        OpKind.add_check_not_valid,
        table="orders",
        column="email",
        line=1,
        constraint="users_email_nn",
    )

    assert check(file_ops[2], file_ops=file_ops, index=2) is not None


def test_validating_a_different_constraint_does_not_suppress() -> None:
    file_ops = not_null_sequence()
    file_ops[1] = make_op(
        OpKind.validate_constraint, table="users", line=2, constraint="users_phone_nn"
    )

    assert check(file_ops[2], file_ops=file_ops, index=2) is not None


def test_the_sequence_must_come_before_the_set_not_null() -> None:
    ordered = not_null_sequence()
    reordered = [ordered[2], ordered[0], ordered[1]]

    assert check(reordered[0], file_ops=reordered, index=0) is not None


def test_mysql_ignores_set_not_null() -> None:
    op = make_op(OpKind.set_not_null, table="users", column="email")

    assert check(op, dialect="mysql") is None


def test_other_operations_are_not_mg001() -> None:
    assert check(make_op(OpKind.drop_table, table="users")) is None
