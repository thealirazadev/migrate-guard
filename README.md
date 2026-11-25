# migrate-guard

A CI linter that catches dangerous database migrations before they reach production. Point it
at your migration files - raw SQL, Laravel migration PHP, or Django migrations - and it flags
the operations that lock hot tables, rewrite millions of rows, or break running code
mid-deploy, each with a stable rule code, a severity, and the safe alternative spelled out as
runnable statements. Nothing is ever executed: SQL is parsed with sqlglot, Django files with
Python's `ast` module, and Laravel files with bounded regexes.

## The problem

A migration that passes review and works perfectly in staging can still take down production:
`CREATE INDEX` without `CONCURRENTLY` blocks every write for the build, an eagerly validated
foreign key locks two tables while it scans, a column rename breaks the previous app version
during the deploy window, and the safe/unsafe line moves between database versions (a
`NOT NULL DEFAULT` column add is a full-table rewrite on Postgres 10 and a metadata change on
11+). Reviewers cannot carry all of that in their heads; migrate-guard encodes it as a CI gate
with the false-positive discipline to be trusted.

## Features

- Nine rules, MG001-MG009: table-rewriting and lock-taking ALTERs, non-concurrent index
  creation, NOT NULL columns without a default or backfill, destructive drops (justification
  required), renames, eagerly validated foreign keys, unique constraints without a concurrent
  index first, enum value removal, and DDL/DML mixing on MySQL. MG000 reports what could not
  be analyzed.
- Dialect and version awareness: `postgres` or `mysql`, with `postgres_version` deciding what
  is actually dangerous. Safe forms are recognized and never flagged.
- Three input formats normalized to one internal operation model: raw SQL, Laravel schema
  builder calls, Django migration operations - all extracted without executing any code.
- `.migrateguard.toml` config: dialect, paths, ignored rules, and per-file allows with a
  mandatory written justification.
- Inline allow comments for per-site waivers, for example
  `-- migrate-guard: allow MG004 reason="audit_legacy retired, OPS-1123"`. An allowed finding
  is still reported with its reason but never gates; a malformed allow exits 2, and an allow
  that matches nothing prints a warning.
- Human-readable text output; exit codes 0/1/2 gate CI.

## Planned

- Diff-base adoption mode: lint only migration files changed since a git ref, so repos with
  years of history start clean.
- JSON and GitHub annotation output, and `--fail-on` as a flag (today `fail_on` is set in the
  config file).
- A composite GitHub Action wrapping the CLI, with PR-aware diff-base defaults.

## Quick start

```bash
uv sync
uv run migrate-guard check db/migrations --dialect postgres --postgres-version 16
uv run migrate-guard rules          # list every rule code
uv run migrate-guard explain MG002  # full explanation of one rule
```

`check` reads `./.migrateguard.toml` when present (or the file given with `--config`); the
`--dialect` and `--postgres-version` flags override it. Exit code 0 means clean, 1 means a
gating finding, 2 means the run failed, for example a bad config or a malformed allow.

## Stack

- Python 3.12
- sqlglot (SQL parsing), Click (CLI)
- pytest, ruff, black; uv with committed lockfile
- Distributed as a pip package plus a composite GitHub Action

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Stack rationale, components, data model, rule catalog, flows, failure modes, invariants |
| [docs/design.md](docs/design.md) | CLI UX: output layouts, color, errors, exit codes |
| [docs/testing.md](docs/testing.md) | Test strategy, commands, CI |
| [docs/api-contracts.md](docs/api-contracts.md) | CLI commands, config file, allow grammar, JSON schema, action inputs |
| [docs/decisions.md](docs/decisions.md) | Design decisions and the reasons behind them |

## Status

Work in progress. Implemented today: the `check`, `rules` and `explain` commands, all nine rules
plus MG000 diagnostics, the SQL, Laravel and Django extractors, strict `.migrateguard.toml`
validation, the `ignore` list, config and inline allows, `--dialect` and `--postgres-version`,
and the text reporter with 0/1/2 exit codes. Not built yet: diff-base mode, JSON and GitHub
output, `--fail-on` as a flag, and the GitHub Action. Those parts of `docs/` describe planned
behavior.
