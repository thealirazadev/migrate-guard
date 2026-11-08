"""Django operations carry Django's default table names, and package markers are skipped."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from migrate_guard.cli import cli
from migrate_guard.extractors import django

CREATE_WITH_UNIQUE = """from django.db import migrations, models


class Migration(migrations.Migration):
    operations = [
        migrations.CreateModel(
            name="ContentType",
            fields=[("id", models.AutoField(primary_key=True))],
        ),
        migrations.AlterUniqueTogether(
            name="contenttype", unique_together={("app_label", "model")}
        ),
    ]
"""

ALTER_AND_REMOVE = """from django.db import migrations, models


class Migration(migrations.Migration):
    operations = [
        migrations.AlterField(
            model_name="user", name="email", field=models.EmailField(max_length=254)
        ),
        migrations.RemoveField("contenttype", "name"),
    ]
"""


def test_operations_get_app_table_and_field_names() -> None:
    ops = django.extract("auth/migrations/0003.py", ALTER_AND_REMOVE, "postgres").operations
    assert [(op.table, op.column) for op in ops] == [
        ("auth_user", "email"),
        ("auth_contenttype", "name"),
    ]


def test_a_unique_constraint_on_a_table_created_in_the_same_file_is_safe(tmp_path: Path) -> None:
    migrations = tmp_path / "contenttypes" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "__init__.py").write_text("")
    (migrations / "0001_initial.py").write_text(CREATE_WITH_UNIQUE)

    result = CliRunner().invoke(cli, ["check", "--dialect", "postgres", str(migrations)])

    assert result.exit_code == 0, result.output
    assert "MG000" not in result.output  # the empty package marker is not reported


def test_findings_name_the_real_column(tmp_path: Path) -> None:
    migrations = tmp_path / "auth" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "0003_alter_email.py").write_text(ALTER_AND_REMOVE)

    result = CliRunner().invoke(cli, ["check", "--dialect", "postgres", str(migrations)])

    assert result.exit_code == 1
    assert "auth_user.email" in result.output
    assert "the table" not in result.output.split("fix:")[0]
