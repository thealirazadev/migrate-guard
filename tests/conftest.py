from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from migrate_guard.cli import cli
from migrate_guard.ir import Operation, OpKind, SourceSpan

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
SQL_UNSAFE = "tests/fixtures/sql/unsafe"
SQL_SAFE = "tests/fixtures/sql/safe"


@pytest.fixture
def run_cli(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Result]:
    """Invoke the CLI from the repository root with color disabled."""
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv("NO_COLOR", "1")
    runner = CliRunner()

    def run(*args: str) -> Result:
        return runner.invoke(cli, list(args))

    return run


@pytest.fixture
def golden() -> Callable[[str], str]:
    def read(name: str) -> str:
        return (FIXTURES / "golden" / name).read_text(encoding="utf-8")

    return read


def make_op(
    kind: OpKind,
    table: str | None = None,
    column: str | None = None,
    line: int = 1,
    raw: str = "",
    **details: object,
) -> Operation:
    """Hand-build an operation for rule unit tests."""
    return Operation(
        kind=kind,
        span=SourceSpan(file="db/migrations/0001_test.sql", line=line),
        raw=raw,
        table=table,
        column=column,
        details=dict(details),
    )
