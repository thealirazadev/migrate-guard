from __future__ import annotations

import pytest
from conftest import make_op

from migrate_guard.config import Config
from migrate_guard.ir import Finding, OpKind
from migrate_guard.rules import mg001, mg003, rules_for

RULE = mg003.RULE
DIALECTS = ("postgres", "mysql")
VERSIONS = (10, 11, 12, 16)


def check(op: object, dialect: str = "postgres", version: int = 16) -> Finding | None:
    return RULE.check(op, [op], 0, Config(dialect=dialect, postgres_version=version))


def added_column(**details: object) -> object:
    return make_op(
        OpKind.add_column,
        table="users",
        column="status",
        line=2,
        raw="ALTER TABLE users ADD COLUMN status text NOT NULL",
        type="text",
        **details,
    )


def test_the_rule_applies_to_both_dialects() -> None:
    assert RULE in rules_for("postgres")
    assert RULE in rules_for("mysql")


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("version", VERSIONS)
def test_not_null_without_a_default_always_fires(dialect: str, version: int) -> None:
    op = added_column(not_null=True, has_default=False, default_volatile=False)
    finding = check(op, dialect, version)

    assert finding is not None
    assert finding.code == "MG003"
    assert finding.severity == "error"
    assert finding.span.line == 2
    assert "status" in finding.message and "users" in finding.message
    assert "backfill" in finding.safe_alternative


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("version", VERSIONS)
def test_a_default_removes_mg003_entirely(dialect: str, version: int) -> None:
    op = added_column(not_null=True, has_default=True, default_volatile=False)

    assert check(op, dialect, version) is None


@pytest.mark.parametrize("dialect", DIALECTS)
def test_a_nullable_column_is_never_mg003(dialect: str) -> None:
    op = added_column(not_null=False, has_default=False, default_volatile=False)

    assert check(op, dialect) is None


@pytest.mark.parametrize("version", VERSIONS)
def test_the_default_case_belongs_to_mg001_or_to_nobody(version: int) -> None:
    """The MG001(b) seam: with a default present exactly one of the two can fire."""
    op = added_column(not_null=True, has_default=True, default_volatile=False)
    config = Config(dialect="postgres", postgres_version=version)

    codes = [
        finding.code
        for finding in (RULE.check(op, [op], 0, config), mg001.RULE.check(op, [op], 0, config))
        if finding is not None
    ]

    assert codes == (["MG001"] if version < 11 else [])


def test_other_operations_are_not_mg003() -> None:
    assert check(make_op(OpKind.set_not_null, table="users", column="status")) is None
