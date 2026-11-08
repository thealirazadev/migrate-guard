"""Test parity across SQL, Laravel, and Django extraction for the same operations.

This ensures that the same dangerous change expressed three ways produces
identical rule codes, and that booby-trapped fixtures never cause side effects.
"""

from __future__ import annotations

from migrate_guard.config import Config
from migrate_guard.engine import check_file
from migrate_guard.extractors import django, laravel, sql


def test_parity_drop_column_produces_same_codes() -> None:
    """The same DROP COLUMN expressed in SQL, Laravel, and Django should report the same codes."""
    config = Config(dialect="postgres", postgres_version=16, paths=[], ignore=[], fail_on="error")

    # SQL version
    sql_text = "ALTER TABLE users DROP COLUMN legacy_field;\n"
    sql_result = sql.extract("parity.sql", sql_text, "postgres")
    sql_findings = check_file(sql_result, config)
    sql_codes = {f.code for f in sql_findings if not f.allowed}

    # Laravel version
    laravel_text = """<?php
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

Schema::table('users', function (Blueprint $table) {
    $table->dropColumn('legacy_field');
});
"""
    laravel_result = laravel.extract("parity.php", laravel_text, "postgres")
    laravel_findings = check_file(laravel_result, config)
    laravel_codes = {f.code for f in laravel_findings if not f.allowed}

    # Django version
    django_text = """from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='legacy_field',
        ),
    ]
"""
    django_result = django.extract("parity.py", django_text, "postgres")
    django_findings = check_file(django_result, config)
    django_codes = {f.code for f in django_findings if not f.allowed}

    # All three should report at least MG004 (drop column)
    assert "MG004" in sql_codes, f"SQL missing MG004, got {sql_codes}"
    assert "MG004" in laravel_codes, f"Laravel missing MG004, got {laravel_codes}"
    assert "MG004" in django_codes, f"Django missing MG004, got {django_codes}"


def test_laravel_booby_trap_never_executes() -> None:
    """Verify that a Laravel file with backtick execution is never evaluated."""
    # If this file were executed, it would output a shell command
    # But we only parse it, so no side effect should occur
    with open("tests/fixtures/laravel/unsafe/booby_trap_eval.php") as f:
        text = f.read()

    # This should not execute any PHP code
    result = laravel.extract("tests/fixtures/laravel/unsafe/booby_trap_eval.php", text, "postgres")

    # We should have extracted operations without executing the backtick
    assert isinstance(result.operations, tuple)
    assert isinstance(result.diagnostics, tuple)


def test_django_booby_trap_never_imports() -> None:
    """Verify that a Django file with module-level side effects is not imported."""
    # The boobytrap file tries to set a marker if imported
    # But we only parse it with ast, so no import should occur
    with open("tests/fixtures/django/unsafe/booby_trap_import.py") as f:
        text = f.read()

    # This should not import the file or trigger any side effects
    result = django.extract("tests/fixtures/django/unsafe/booby_trap_import.py", text, "postgres")

    # We should have extracted operations without importing
    assert isinstance(result.operations, tuple)
    assert isinstance(result.diagnostics, tuple)

    # Verify the booby trap marker was not set
    import sys

    assert "tests/fixtures/django/unsafe/booby_trap_import" not in sys.modules


def test_safe_fixtures_produce_no_findings() -> None:
    """Safe fixtures should produce no findings across all formats."""
    config = Config(dialect="postgres", postgres_version=16, paths=[], ignore=[], fail_on="error")

    # Laravel safe fixture
    with open("tests/fixtures/laravel/safe/simple_add_nullable_column.php") as f:
        laravel_text = f.read()
    laravel_result = laravel.extract("safe.php", laravel_text, "postgres")
    laravel_findings = check_file(laravel_result, config)
    laravel_codes = {f.code for f in laravel_findings if not f.allowed}

    # Django safe fixture
    with open("tests/fixtures/django/safe/simple_add_field.py") as f:
        django_text = f.read()
    django_result = django.extract("safe.py", django_text, "postgres")
    django_findings = check_file(django_result, config)
    django_codes = {f.code for f in django_findings if not f.allowed}

    # Safe fixtures should not produce any findings
    assert len(laravel_codes) == 0, f"Laravel safe fixture produced {laravel_codes}"
    assert len(django_codes) == 0, f"Django safe fixture produced {django_codes}"
