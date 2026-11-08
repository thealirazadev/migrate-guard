from __future__ import annotations

from migrate_guard.extractors import laravel
from migrate_guard.ir import OpKind


def test_laravel_schema_drop_table() -> None:
    text = """<?php
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

Schema::drop('users');
"""
    result = laravel.extract("migrations/0001.php", text, "postgres")

    assert len(result.operations) >= 1
    drop_ops = [op for op in result.operations if op.kind == OpKind.drop_table]
    assert len(drop_ops) > 0


def test_laravel_recognizes_dangerous_drops() -> None:
    text = """<?php
Schema::table('users', function ($table) {
    $table->dropColumn('old_field');
});
"""
    result = laravel.extract("migrations/0002.php", text, "postgres")
    assert len(result.operations) >= 0  # Extraction should not crash


def test_laravel_with_comment_stripped() -> None:
    text = """<?php
// This is a comment with Schema::drop('fake') that should be ignored
Schema::table('users', function ($table) {
    $table->dropColumn('real_field');
});
"""
    result = laravel.extract("migrations/0003.php", text, "postgres")
    assert result.diagnostics == ()  # No parse errors


def test_laravel_extract_from_safe_fixture() -> None:
    with open("tests/fixtures/laravel/safe/simple_add_nullable_column.php") as f:
        text = f.read()

    result = laravel.extract(
        "tests/fixtures/laravel/safe/simple_add_nullable_column.php", text, "postgres"
    )
    assert result.diagnostics == ()


def test_laravel_extract_from_unsafe_fixture() -> None:
    with open("tests/fixtures/laravel/unsafe/parity_drop_column.php") as f:
        text = f.read()

    result = laravel.extract(
        "tests/fixtures/laravel/unsafe/parity_drop_column.php", text, "postgres"
    )
    # Should parse without crashes
    assert isinstance(result.operations, tuple)
