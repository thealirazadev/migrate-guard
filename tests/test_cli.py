from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import Result
from conftest import MYSQL_SAFE, MYSQL_UNSAFE, SQL_SAFE, SQL_UNSAFE

from migrate_guard import __version__

FINDING_LINE = re.compile(r"^\s*(\d+)\s+(MG\d{3})\s+(error|warning)\s")


def codes(output: str) -> list[str]:
    """The rule codes reported, in the order the report lists them."""
    return [match[2] for line in output.splitlines() if (match := FINDING_LINE.match(line))]


def test_unsafe_fixtures_gate_the_run(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", SQL_UNSAFE, "--dialect", "postgres")

    assert result.exit_code == 1
    assert "MG002" in result.stdout
    assert "MG004" in result.stdout
    assert "verdict: FAIL (fail_on = error)" in result.stdout


def test_safe_fixtures_pass(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", SQL_SAFE, "--dialect", "postgres")

    assert result.exit_code == 0
    assert "no problems found" in result.stdout
    assert "verdict: PASS (fail_on = error)" in result.stdout


def test_mg000_does_not_gate_but_is_reported(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", f"{SQL_UNSAFE}/0044_garbage.sql", "--dialect", "postgres")

    assert "  3  MG000  warning" in result.stdout
    assert "0 allowed" in result.stdout


def test_a_multi_action_alter_is_reported_instead_of_vanishing(
    run_cli: Callable[..., Result], tmp_path: Path
) -> None:
    """The drop hides inside a statement sqlglot keeps as a raw command."""
    migration = tmp_path / "0100_multi_action.sql"
    migration.write_text(
        "ALTER TABLE users ADD COLUMN a int, DROP COLUMN legacy_flag;\n", encoding="utf-8"
    )
    result = run_cli("check", str(migration), "--dialect", "postgres")

    assert codes(result.stdout) == ["MG000"]
    assert "no problems found" not in result.stdout


def test_a_pathological_statement_does_not_abort_the_run(
    run_cli: Callable[..., Result], tmp_path: Path
) -> None:
    """One file the parser chokes on must not take the other files down with it."""
    deep = "SELECT " + "(" * 400 + "1" + ")" * 400
    (tmp_path / "0100_deep.sql").write_text(f"{deep};\n", encoding="utf-8")
    (tmp_path / "0101_drop.sql").write_text("DROP TABLE audit_legacy;\n", encoding="utf-8")

    result = run_cli("check", str(tmp_path), "--dialect", "postgres")

    assert result.exit_code == 1
    assert codes(result.stdout) == ["MG000", "MG004"]
    assert "internal error" not in result.stderr


def test_dialect_gate_changes_the_verdict(run_cli: Callable[..., Result]) -> None:
    postgres = run_cli("check", f"{SQL_UNSAFE}/0042_add_email_index.sql", "--dialect", "postgres")
    mysql = run_cli("check", f"{SQL_UNSAFE}/0042_add_email_index.sql", "--dialect", "mysql")

    assert postgres.exit_code == 1
    assert mysql.exit_code == 0


def test_two_runs_are_byte_identical(run_cli: Callable[..., Result]) -> None:
    first = run_cli("check", SQL_UNSAFE, "--dialect", "postgres")
    second = run_cli("check", SQL_UNSAFE, "--dialect", "postgres")

    assert first.stdout == second.stdout


def test_config_paths_are_used_when_no_paths_are_given(
    run_cli: Callable[..., Result], tmp_path: Path
) -> None:
    config = tmp_path / ".migrateguard.toml"
    config.write_text(
        f'[migrate-guard]\ndialect = "postgres"\npaths = ["{SQL_SAFE}"]\n', encoding="utf-8"
    )
    result = run_cli("check", "--config", str(config))

    assert result.exit_code == 0
    assert "checked 8 files" in result.stdout


def test_cli_paths_override_configured_paths(
    run_cli: Callable[..., Result], tmp_path: Path
) -> None:
    config = tmp_path / ".migrateguard.toml"
    config.write_text(
        f'[migrate-guard]\ndialect = "postgres"\npaths = ["{SQL_SAFE}"]\n', encoding="utf-8"
    )
    result = run_cli("check", SQL_UNSAFE, "--config", str(config))

    assert result.exit_code == 1


def test_config_errors_exit_two_with_empty_stdout(
    run_cli: Callable[..., Result], tmp_path: Path
) -> None:
    config = tmp_path / ".migrateguard.toml"
    config.write_text('[migrate-guard]\ndialect = "postgres"\nignroe = []\n', encoding="utf-8")
    result = run_cli("check", SQL_SAFE, "--config", str(config))

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.startswith('error: unknown key "ignroe"')
    assert len(result.stderr.splitlines()) == 1


def test_missing_dialect_exits_two_with_a_remedy_line(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", SQL_SAFE)

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        "error: no dialect configured",
        'add dialect = "postgres" to .migrateguard.toml or pass --dialect',
    ]


def test_missing_path_exits_two(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", "does/not/exist", "--dialect", "postgres")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == "error: path does/not/exist does not exist\n"


def test_no_paths_at_all_exits_two(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", "--dialect", "postgres")

    assert result.exit_code == 2
    assert result.stderr.startswith("error: no paths to check")


def test_bad_dialect_flag_is_rejected(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", SQL_SAFE, "--dialect", "sqlite")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "'sqlite' is not one of 'postgres', 'mysql'" in result.stderr


def test_version_and_help(run_cli: Callable[..., Result]) -> None:
    version = run_cli("--version")
    help_text = run_cli("check", "--help")

    assert version.exit_code == 0
    assert version.stdout == f"migrate-guard {__version__}\n"
    assert help_text.exit_code == 0
    assert "--dialect" in help_text.stdout


POSTGRES_MATRIX = [
    ("0042_add_email_index.sql", ["MG002"]),
    ("0043_cleanup.sql", ["MG004", "MG004"]),
    ("0044_garbage.sql", ["MG002", "MG000", "MG004"]),
    ("0045_widen_email.sql", ["MG001"]),
    ("0046_add_status.sql", ["MG003"]),
    ("0047_enforce_email.sql", ["MG001"]),
    ("0048_rename_email.sql", ["MG005", "MG005"]),
    ("0049_orders_user_fk.sql", ["MG006"]),
    ("0050_unique_email.sql", ["MG007"]),
    ("0051_drop_status_type.sql", ["MG008"]),
    ("0052_add_created_at.sql", ["MG001"]),
]

MYSQL_MATRIX = [
    ("0001_modify_email.sql", ["MG001"]),
    ("0002_add_status.sql", ["MG003"]),
    ("0003_cleanup.sql", ["MG004", "MG004"]),
    ("0004_rename_email.sql", ["MG001", "MG005"]),
    ("0005_status_enum.sql", ["MG008"]),
    ("0006_backfill_status.sql", ["MG009"]),
]


@pytest.mark.parametrize(("name", "expected"), POSTGRES_MATRIX)
def test_each_postgres_unsafe_fixture_reports_its_codes(
    run_cli: Callable[..., Result], name: str, expected: list[str]
) -> None:
    result = run_cli("check", f"{SQL_UNSAFE}/{name}", "--dialect", "postgres")

    assert codes(result.stdout) == expected


@pytest.mark.parametrize(("name", "expected"), MYSQL_MATRIX)
def test_each_mysql_unsafe_fixture_reports_its_codes(
    run_cli: Callable[..., Result], name: str, expected: list[str]
) -> None:
    result = run_cli("check", f"{MYSQL_UNSAFE}/{name}", "--dialect", "mysql")

    assert codes(result.stdout) == expected


@pytest.mark.parametrize(("paths", "dialect"), [(SQL_SAFE, "postgres"), (MYSQL_SAFE, "mysql")])
def test_every_safe_fixture_stays_quiet(
    run_cli: Callable[..., Result], paths: str, dialect: str
) -> None:
    result = run_cli("check", paths, "--dialect", dialect)

    assert result.exit_code == 0
    assert codes(result.stdout) == []
    assert "no problems found" in result.stdout


def test_mysql_unsafe_fixtures_gate_the_run(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", MYSQL_UNSAFE, "--dialect", "mysql")

    assert result.exit_code == 1
    assert set(codes(result.stdout)) == {"MG001", "MG003", "MG004", "MG005", "MG008", "MG009"}


def test_postgres_only_rules_never_fire_under_mysql(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", SQL_UNSAFE, "--dialect", "mysql")

    assert {"MG002", "MG006", "MG007"}.isdisjoint(codes(result.stdout))


def test_mysql_only_rules_never_fire_under_postgres(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", MYSQL_UNSAFE, "--dialect", "postgres")

    assert "MG009" not in codes(result.stdout)


@pytest.mark.parametrize(
    ("version", "expected"),
    [(10, ["MG001"]), (11, []), (12, []), (16, [])],
)
def test_a_constant_default_depends_on_the_postgres_version(
    run_cli: Callable[..., Result], version: int, expected: list[str]
) -> None:
    result = run_cli(
        "check",
        f"{SQL_SAFE}/0003_add_status_with_default.sql",
        "--dialect",
        "postgres",
        "--postgres-version",
        str(version),
    )

    assert codes(result.stdout) == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    [(10, ["MG001"]), (11, ["MG001"]), (12, []), (16, [])],
)
def test_the_not_null_check_sequence_depends_on_the_postgres_version(
    run_cli: Callable[..., Result], version: int, expected: list[str]
) -> None:
    result = run_cli(
        "check",
        f"{SQL_SAFE}/0004_enforce_email.sql",
        "--dialect",
        "postgres",
        "--postgres-version",
        str(version),
    )

    assert codes(result.stdout) == expected


def test_a_bad_postgres_version_exits_two(run_cli: Callable[..., Result]) -> None:
    result = run_cli("check", SQL_SAFE, "--dialect", "postgres", "--postgres-version", "0")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == "error: invalid --postgres-version 0; it must be a positive integer\n"


def test_rules_lists_every_documented_code(run_cli: Callable[..., Result]) -> None:
    result = run_cli("rules")

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert [line.split("  ")[0] for line in lines] == [f"MG00{n}" for n in range(10)]
    assert lines[0] == (
        "MG000  warning  postgres,mysql  statement or file that could not be analyzed"
    )
    assert lines[2] == "MG002  error    postgres        CREATE INDEX without CONCURRENTLY"
    assert lines[9] == "MG009  warning  mysql           DDL and DML mixed in one migration"


def test_explain_prints_the_long_form(run_cli: Callable[..., Result]) -> None:
    result = run_cli("explain", "MG001")

    assert result.exit_code == 0
    assert result.stdout.startswith("MG001  error  postgres,mysql\n")
    assert "ALTER that rewrites or scan-locks the table" in result.stdout
    assert "ACCESS EXCLUSIVE" in result.stdout
    assert "migrate-guard: allow MG001 reason=" in result.stdout


def test_explain_accepts_a_lower_case_code(run_cli: Callable[..., Result]) -> None:
    assert run_cli("explain", "mg004").stdout == run_cli("explain", "MG004").stdout


def test_explain_covers_the_diagnostic_code(run_cli: Callable[..., Result]) -> None:
    result = run_cli("explain", "MG000")

    assert result.exit_code == 0
    assert "MG000 is a diagnostic" in result.stdout


def test_explain_rejects_an_unknown_code(run_cli: Callable[..., Result]) -> None:
    result = run_cli("explain", "MG999")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == (
        'error: unknown rule code "MG999"; run migrate-guard rules for the list\n'
    )
