from __future__ import annotations

from pathlib import Path

import pytest

from migrate_guard.config import MigrateGuardError, load_config


def write(tmp_path: Path, body: str) -> str:
    path = tmp_path / ".migrateguard.toml"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_defaults_apply(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, '[migrate-guard]\ndialect = "postgres"\n'))
    assert config.dialect == "postgres"
    assert config.postgres_version == 16
    assert config.fail_on == "error"
    assert config.paths == ()
    assert config.ignore == ()
    assert config.allow == ()


def test_full_document_parses(tmp_path: Path) -> None:
    config = load_config(
        write(
            tmp_path,
            """
[migrate-guard]
dialect = "mysql"
postgres_version = 12
paths = ["db/migrations"]
ignore = ["MG009"]
fail_on = "warning"

[[migrate-guard.allow]]
file = "db/migrations/0043_cleanup.sql"
rules = ["MG004"]
reason = "  audit_legacy retired 2026-06  "
""",
        )
    )
    assert config.dialect == "mysql"
    assert config.postgres_version == 12
    assert config.paths == ("db/migrations",)
    assert config.ignore == ("MG009",)
    assert config.fail_on == "warning"
    assert config.allow[0].reason == "audit_legacy retired 2026-06"


def test_cli_dialect_overrides_config(tmp_path: Path) -> None:
    path = write(tmp_path, '[migrate-guard]\ndialect = "postgres"\n')
    assert load_config(path, "mysql").dialect == "mysql"


def test_missing_dialect_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(MigrateGuardError) as excinfo:
        load_config(write(tmp_path, "[migrate-guard]\npaths = []\n"))
    assert "no dialect configured" in excinfo.value.message
    assert excinfo.value.remedy is not None


def test_unknown_key_names_the_key_and_accepted_list(tmp_path: Path) -> None:
    with pytest.raises(MigrateGuardError) as excinfo:
        load_config(write(tmp_path, '[migrate-guard]\ndialect = "postgres"\nignroe = []\n'))
    message = excinfo.value.message
    assert '"ignroe"' in message
    assert "(line 3)" in message
    assert "accepted keys: dialect, postgres_version, paths, ignore, fail_on, allow" in message


def test_unknown_table_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(MigrateGuardError, match="unknown table"):
        load_config(write(tmp_path, '[migrateguard]\ndialect = "postgres"\n'))


def test_invalid_toml_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(MigrateGuardError, match="invalid TOML"):
        load_config(write(tmp_path, "[migrate-guard\ndialect =\n"))


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('dialect = "sqlite"', 'invalid dialect "sqlite"'),
        ('dialect = "postgres"\npostgres_version = "16"', "positive integer"),
        ('dialect = "postgres"\npostgres_version = 0', "positive integer"),
        ('dialect = "postgres"\nfail_on = "panic"', 'invalid fail_on "panic"'),
        ('dialect = "postgres"\npaths = "db"', "must be a list of strings"),
        ('dialect = "postgres"\nignore = ["nope"]', 'invalid rule code "nope"'),
    ],
)
def test_value_validation(tmp_path: Path, body: str, expected: str) -> None:
    with pytest.raises(MigrateGuardError) as excinfo:
        load_config(write(tmp_path, f"[migrate-guard]\n{body}\n"))
    assert expected in excinfo.value.message


@pytest.mark.parametrize("code", ["MG004", "MG000"])
def test_undroppable_codes_cannot_be_ignored(tmp_path: Path, code: str) -> None:
    with pytest.raises(MigrateGuardError) as excinfo:
        load_config(
            write(tmp_path, f'[migrate-guard]\ndialect = "postgres"\nignore = ["{code}"]\n')
        )
    assert f"{code} cannot be ignored globally" in excinfo.value.message


def test_allow_entry_needs_a_reason(tmp_path: Path) -> None:
    body = """
[migrate-guard]
dialect = "postgres"

[[migrate-guard.allow]]
file = "db/migrations/0043_cleanup.sql"
rules = ["MG004"]
reason = "   "
"""
    with pytest.raises(MigrateGuardError, match="has no reason"):
        load_config(write(tmp_path, body))


def test_explicit_missing_config_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(MigrateGuardError, match="does not exist"):
        load_config(str(tmp_path / "absent.toml"))


def test_absent_default_config_is_fine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_config(None, "postgres").dialect == "postgres"
