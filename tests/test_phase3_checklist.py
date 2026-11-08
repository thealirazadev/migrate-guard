"""Phase 3 checklist items that had no test: atomic rule, unextractable calls, regex bounds."""

from __future__ import annotations

import time
from pathlib import Path

from click.testing import CliRunner

from migrate_guard.cli import cli
from migrate_guard.extractors import laravel

CONCURRENT = """from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
{atomic}
    operations = [
        AddIndexConcurrently(
            model_name="order", index=models.Index(fields=["created"], name="order_created_idx")
        ),
    ]
"""


def check(tmp_path: Path, name: str, text: str) -> str:
    folder = tmp_path / "shop" / "migrations"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text)
    result = CliRunner().invoke(cli, ["check", "--dialect", "postgres", str(folder)])
    return result.output


def test_add_index_concurrently_needs_atomic_false(tmp_path: Path) -> None:
    unsafe = check(tmp_path / "a", "0002_idx.py", CONCURRENT.format(atomic=""))
    safe = check(tmp_path / "b", "0002_idx.py", CONCURRENT.format(atomic="    atomic = False\n"))
    assert "MG002" in unsafe and "atomic" in unsafe.lower()
    assert "MG002" not in safe


def test_db_statement_with_a_variable_is_mg000_not_a_guess() -> None:
    text = "<?php\nfunction up() {\n    DB::statement($sql);\n}\n"
    result = laravel.extract("m.php", text, "postgres")
    assert [d.code for d in result.diagnostics] == ["MG000"]
    assert not result.operations


def test_schema_calls_inside_comments_yield_nothing() -> None:
    text = (
        "<?php\nfunction up() {\n"
        "    // Schema::drop('users');\n"
        "    /* Schema::table('t', function ($t) { $t->dropColumn('x'); }); */\n"
        "}\n"
    )
    assert not laravel.extract("m.php", text, "postgres").operations


def test_a_one_megabyte_single_line_file_finishes_quickly() -> None:
    text = "<?php " + "$x = 'Schema::table(' . $y; " * 40_000
    assert len(text) > 1_000_000
    started = time.perf_counter()
    laravel.extract("big.php", text, "postgres")
    assert time.perf_counter() - started < 1.0
