from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from click.testing import Result
from conftest import SQL_SAFE, SQL_UNSAFE

from migrate_guard import __version__


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
    assert "checked 2 files" in result.stdout


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
