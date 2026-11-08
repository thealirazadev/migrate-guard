"""Laravel migrations: only up() runs on deploy, so down() must never produce findings."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from migrate_guard.cli import cli
from migrate_guard.extractors import laravel
from migrate_guard.ir import OpKind

CREATE_TABLE = """<?php

use Illuminate\\Database\\Migrations\\Migration;
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('links', function (Blueprint $table) {
            $table->id();
            $table->string('code')->unique();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('links');
    }
};
"""

DROP_IN_UP = """<?php

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn('legacy_flag');
        });
        Schema::dropIfExists('old_sessions');
    }

    public function down(): void
    {
        Schema::create('old_sessions', function (Blueprint $table) {
            $table->id();
        });
    }
};
"""


def kinds(text: str) -> list[OpKind]:
    return [op.kind for op in laravel.extract("m.php", text, "postgres").operations]


def test_the_rollback_drop_in_down_is_ignored() -> None:
    assert OpKind.drop_table not in kinds(CREATE_TABLE)


def test_drops_in_up_are_still_extracted_at_their_real_lines() -> None:
    operations = laravel.extract("m.php", DROP_IN_UP, "postgres").operations
    by_kind = {op.kind: op.span.line for op in operations}
    assert by_kind[OpKind.drop_column] == 8
    assert by_kind[OpKind.drop_table] == 10


def test_a_file_without_up_is_scanned_whole() -> None:
    assert OpKind.drop_table in kinds("<?php\nSchema::drop('users');\n")


def test_check_passes_a_standard_create_migration_and_fails_a_drop(tmp_path: Path) -> None:
    (tmp_path / "2026_01_01_000000_create_links_table.php").write_text(CREATE_TABLE)
    runner = CliRunner()
    ok = runner.invoke(cli, ["check", "--dialect", "postgres", str(tmp_path)])
    assert ok.exit_code == 0, ok.output

    (tmp_path / "2026_01_02_000000_drop_old_sessions.php").write_text(DROP_IN_UP)
    bad = runner.invoke(cli, ["check", "--dialect", "postgres", str(tmp_path)])
    assert bad.exit_code == 1
    assert "MG004" in bad.output and "old_sessions" in bad.output
