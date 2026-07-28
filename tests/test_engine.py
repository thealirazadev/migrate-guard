from __future__ import annotations

from conftest import make_op

from migrate_guard.config import Config
from migrate_guard.engine import check_file, sort_findings
from migrate_guard.extractors import ExtractionResult
from migrate_guard.ir import Finding, OpKind, SourceSpan

POSTGRES = Config(dialect="postgres")


def result_for(*operations: object, diagnostics: tuple[Finding, ...] = ()) -> ExtractionResult:
    return ExtractionResult(operations=tuple(operations), diagnostics=diagnostics)


def test_operations_on_a_table_created_here_are_exempt() -> None:
    findings = check_file(
        result_for(
            make_op(OpKind.create_table, table="sessions", line=1),
            make_op(OpKind.create_index, table="sessions", line=2, unique=False, concurrent=False),
            make_op(OpKind.drop_column, table="sessions", column="scratch", line=3),
        ),
        POSTGRES,
    )

    assert findings == []


def test_the_exemption_ignores_identifier_case() -> None:
    findings = check_file(
        result_for(
            make_op(OpKind.create_table, table="Sessions", line=1),
            make_op(OpKind.drop_table, table="sessions", line=2),
        ),
        POSTGRES,
    )

    assert findings == []


def test_other_tables_are_still_checked() -> None:
    findings = check_file(
        result_for(
            make_op(OpKind.create_table, table="sessions", line=1),
            make_op(OpKind.drop_table, table="users", line=2),
        ),
        POSTGRES,
    )

    assert [finding.code for finding in findings] == ["MG004"]


def test_diagnostics_are_carried_through() -> None:
    diagnostic = Finding(
        code="MG000",
        severity="warning",
        span=SourceSpan("db/migrations/0001_test.sql", 9),
        message="unparseable",
        safe_alternative="review by hand",
        statement="???",
    )
    findings = check_file(
        result_for(make_op(OpKind.drop_table, table="users", line=1), diagnostics=(diagnostic,)),
        POSTGRES,
    )

    assert [finding.code for finding in findings] == ["MG004", "MG000"]


def test_dialect_gates_are_hard() -> None:
    operations = result_for(
        make_op(OpKind.create_index, table="users", line=1, unique=False, concurrent=False)
    )

    assert [f.code for f in check_file(operations, POSTGRES)] == ["MG002"]
    assert check_file(operations, Config(dialect="mysql")) == []


def test_findings_sort_by_file_then_line_then_code() -> None:
    def finding(code: str, file: str, line: int) -> Finding:
        return Finding(
            code=code,
            severity="error",
            span=SourceSpan(file, line),
            message="m",
            safe_alternative="s",
            statement="t",
        )

    ordered = sort_findings(
        [
            finding("MG004", "b.sql", 1),
            finding("MG004", "a.sql", 9),
            finding("MG002", "a.sql", 9),
            finding("MG002", "a.sql", 2),
        ]
    )

    assert [(f.span.file, f.span.line, f.code) for f in ordered] == [
        ("a.sql", 2, "MG002"),
        ("a.sql", 9, "MG002"),
        ("a.sql", 9, "MG004"),
        ("b.sql", 1, "MG004"),
    ]


NEW_TABLE_OPS = [
    make_op(OpKind.create_table, table="sessions", line=1),
    make_op(
        OpKind.alter_column_type,
        table="sessions",
        column="token",
        line=2,
        new_type="text",
        old_type=None,
    ),
    make_op(
        OpKind.add_column,
        table="sessions",
        column="a",
        line=3,
        not_null=True,
        has_default=False,
        default_volatile=False,
    ),
    make_op(
        OpKind.add_column,
        table="sessions",
        column="b",
        line=4,
        not_null=True,
        has_default=True,
        default_volatile=True,
    ),
    make_op(OpKind.set_not_null, table="sessions", column="token", line=5),
    make_op(OpKind.create_index, table="sessions", line=6, unique=False, concurrent=False),
    make_op(OpKind.drop_column, table="sessions", column="scratch", line=7),
    make_op(OpKind.rename_column, table="sessions", column="a", line=8, new_name="c"),
    make_op(OpKind.rename_table, table="sessions", line=9, new_name="tokens"),
    make_op(OpKind.add_foreign_key, table="sessions", line=10, not_valid=False),
    make_op(OpKind.add_unique_constraint, table="sessions", line=11, using_index=False),
    make_op(OpKind.redefine_enum, table="sessions", column="kind", line=12),
    make_op(OpKind.dml, table="sessions", line=13, verb="insert"),
]


def test_the_new_table_exemption_covers_every_rule() -> None:
    result = result_for(*NEW_TABLE_OPS)

    assert check_file(result, Config(dialect="postgres", postgres_version=10)) == []
    assert check_file(result, Config(dialect="mysql")) == []


def test_the_same_operations_on_an_existing_table_are_reported() -> None:
    without_create = result_for(*NEW_TABLE_OPS[1:])
    codes = {
        finding.code
        for finding in check_file(without_create, Config(dialect="postgres", postgres_version=10))
    }

    assert codes == {"MG001", "MG002", "MG003", "MG004", "MG005", "MG006", "MG007"}
