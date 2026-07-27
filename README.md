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

## Planned features

- Nine rules, MG001-MG009: table-rewriting and lock-taking ALTERs, non-concurrent index
  creation, NOT NULL columns without a default or backfill, destructive drops (justification
  required), renames, eagerly validated foreign keys, unique constraints without a concurrent
  index first, enum value removal, and DDL/DML mixing on MySQL.
- Dialect and version awareness: `postgres` or `mysql`, with `postgres_version` deciding what
  is actually dangerous. Safe forms are recognized and never flagged.
- Three input formats normalized to one internal operation model: raw SQL, Laravel schema
  builder calls, Django migration operations - all extracted without executing any code.
- `.migrateguard.toml` config: dialect, paths, ignored rules, and per-file allows with a
  mandatory written justification; inline allow comments for per-site waivers.
- Diff-base adoption mode: lint only migration files changed since a git ref, so repos with
  years of history start clean.
- Output as human text, JSON, or GitHub annotations; exit codes gate CI.
- A composite GitHub Action wrapping the CLI, with PR-aware diff-base defaults.

## Stack

- Python 3.12
- sqlglot (SQL parsing), Click (CLI)
- pytest, ruff, black; uv with committed lockfile
- Distributed as a pip package plus a composite GitHub Action

## Documentation

| Document | Contents |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Problem, target user, core features, non-goals, success criteria |
| [docs/architecture.md](docs/architecture.md) | Stack rationale, components, data model, rule catalog, flows, failure modes, invariants |
| [docs/rules.md](docs/rules.md) | Project-specific engineering rules |
| [docs/phases.md](docs/phases.md) | Implementation phases with commit lists and verification checklists |
| [docs/design.md](docs/design.md) | CLI UX: output layouts, color, errors, exit codes |
| [docs/testing.md](docs/testing.md) | Test strategy, commands, CI plan |
| [docs/api-contracts.md](docs/api-contracts.md) | CLI commands, config file, allow grammar, JSON schema, action inputs |
| [docs/launch-checklist.md](docs/launch-checklist.md) | Pre-release checks |
| [docs/memory.md](docs/memory.md) | Working log and decisions |

## Status

This project is in the planning stage: the documents above are the complete specification, and
no implementation code exists yet. Implementation follows `docs/phases.md` phase by phase,
starting with the raw-SQL pipeline. Everything described here is planned behavior, not shipped
behavior.
