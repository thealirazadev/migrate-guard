"""Command line entry point: flags, orchestration, exit codes. No analysis here.

Exit codes are frozen: 0 clean, 1 gating findings, 2 configuration or
environment error. Stdout carries the report and nothing else; on exit 2 it
stays empty, because a partial report is worse than none.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import NoReturn

import click

from . import __version__
from .config import MigrateGuardError, load_config
from .discovery import discover, read_source
from .engine import check_file, sort_findings
from .extractors import sql
from .reporters import text as text_reporter

EXTRACTORS = {"sql": sql.extract}


@click.group()
@click.version_option(__version__, "--version", message="migrate-guard %(version)s")
def cli() -> None:
    """Catch dangerous database migrations before they reach production."""


@cli.command()
@click.argument("paths", nargs=-1)
@click.option(
    "--config",
    "config_path",
    default=None,
    help="Config file to load  [default: ./.migrateguard.toml]",
)
@click.option(
    "--dialect",
    type=click.Choice(["postgres", "mysql"]),
    default=None,
    help="SQL dialect; overrides the config file.",
)
@click.option("--no-color", is_flag=True, help="Force plain output (same as NO_COLOR).")
def check(
    paths: tuple[str, ...],
    config_path: str | None,
    dialect: str | None,
    no_color: bool,
) -> None:
    """Lint migration files in PATHS (or the configured paths) and report findings."""
    try:
        config = load_config(config_path, dialect)
        files = discover(list(paths) or list(config.paths))

        findings = []
        statements = 0
        for migration in files:
            result = EXTRACTORS[migration.format](
                migration.path, read_source(migration.path), config.dialect
            )
            statements += result.statement_count
            findings.extend(check_file(result, config))

        findings = sort_findings(findings)
        report = text_reporter.render(
            findings,
            files_checked=len(files),
            statements_checked=statements,
            config=config,
            color=_use_color(no_color),
        )
        gating = text_reporter.summarize(findings, config.fail_on)["gating"]
    except MigrateGuardError as exc:
        _abort(exc.message, exc.remedy)
    except Exception as exc:  # noqa: BLE001 - the CLI boundary never leaks a traceback
        if os.environ.get("MIGRATE_GUARD_DEBUG") == "1":
            raise
        _abort(f"internal error: {exc}")

    click.echo(report, nl=False)
    sys.exit(1 if gating else 0)


def _use_color(no_color: bool) -> bool:
    return not no_color and not os.environ.get("NO_COLOR") and sys.stdout.isatty()


def _abort(message: str, remedy: str | None = None) -> NoReturn:
    click.echo(f"error: {message}", err=True)
    if remedy:
        click.echo(remedy, err=True)
    sys.exit(2)


def main() -> None:
    # sqlglot logs a warning whenever it falls back to a generic Command node;
    # that is normal for statements this tool does not model, and stderr belongs
    # to migrate-guard's own messages.
    logging.getLogger("sqlglot").setLevel(logging.ERROR)
    cli()


if __name__ == "__main__":
    main()
