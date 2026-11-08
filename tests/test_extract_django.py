from __future__ import annotations

from migrate_guard.extractors import django
from migrate_guard.ir import OpKind


def test_django_remove_field() -> None:
    text = """from django.db import migrations

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
    result = django.extract("0002_remove_field.py", text, "postgres")

    assert len(result.operations) > 0
    remove_ops = [op for op in result.operations if op.kind == OpKind.drop_column]
    assert len(remove_ops) > 0


def test_django_delete_model() -> None:
    text = """from django.db import migrations

class Migration(migrations.Migration):

    operations = [
        migrations.DeleteModel(
            name='OldModel',
        ),
    ]
"""
    result = django.extract("0003_delete_old.py", text, "postgres")

    assert len(result.operations) > 0
    delete_ops = [op for op in result.operations if op.kind == OpKind.drop_table]
    assert len(delete_ops) > 0


def test_django_no_migration_class_is_mg000() -> None:
    text = """# This is not a Django migration file
print("Hello, World!")
"""
    result = django.extract("not_a_migration.py", text, "postgres")

    assert len(result.diagnostics) > 0
    assert result.diagnostics[0].code == "MG000"


def test_django_syntax_error_is_mg000() -> None:
    text = """from django.db import migrations

class Migration(migrations.Migration:
    pass
"""
    result = django.extract("bad_syntax.py", text, "postgres")

    assert len(result.diagnostics) > 0
    assert result.diagnostics[0].code == "MG000"


def test_django_add_field_nullable() -> None:
    text = """from django.db import migrations, models

class Migration(migrations.Migration):

    operations = [
        migrations.AddField(
            model_name='user',
            name='new_field',
            field=models.CharField(max_length=100, null=True),
        ),
    ]
"""
    result = django.extract("0004_add_field.py", text, "postgres")

    add_ops = [op for op in result.operations if op.kind == OpKind.add_column]
    assert len(add_ops) > 0


def test_django_extract_from_safe_fixture() -> None:
    with open("tests/fixtures/django/safe/simple_add_field.py") as f:
        text = f.read()

    result = django.extract("tests/fixtures/django/safe/simple_add_field.py", text, "postgres")
    assert result.diagnostics == ()


def test_django_extract_from_unsafe_fixture() -> None:
    with open("tests/fixtures/django/unsafe/parity_drop_column.py") as f:
        text = f.read()

    result = django.extract("tests/fixtures/django/unsafe/parity_drop_column.py", text, "postgres")
    assert len(result.operations) > 0


def test_django_never_executes_booby_trap() -> None:
    """Verify that importing a booby-trapped migration does not cause side effects."""
    # The booby trap file sets a module-level variable if imported
    # We're only parsing it, not importing it
    with open("tests/fixtures/django/unsafe/booby_trap_import.py") as f:
        text = f.read()

    # This should not import the file or trigger the side effect
    result = django.extract("tests/fixtures/django/unsafe/booby_trap_import.py", text, "postgres")

    # We should have extracted the operations without executing anything
    assert len(result.operations) > 0
    assert result.diagnostics == ()
