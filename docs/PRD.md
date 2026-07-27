# Product Requirements - migrate-guard

## What we're building

A CI linter that catches dangerous database migrations before they reach production.
`migrate-guard check` scans migration files - raw SQL, Laravel migration PHP (regex-assisted
extraction of schema builder calls), and Django migrations (static AST introspection of the
operations list) - without ever executing any of them. Every dangerous operation is reported with
a stable rule code (MG001-MG009), a severity, the offending statement and line, and an explanation
that includes the safe alternative. Output is human text, JSON, or GitHub annotations; exit codes
gate CI. A `.migrateguard.toml` config sets the SQL dialect and target version, ignored rules, and
a per-file allowlist that requires a written justification. A diff-base mode lints only new or
changed migration files so an existing repository adopts the tool without fixing its history.
Distributed as a pip package plus a composite GitHub Action wrapping the CLI.

## Target user

A backend team on Postgres or MySQL that ships schema changes through pull requests and has been
burned - or is afraid of being burned - by a migration that locked a hot table, rewrote a hundred
million rows, or broke running application code mid-deploy. Reviewers cannot be expected to
remember the lock semantics of every ALTER form on every database version; migrate-guard encodes
that knowledge as a review gate. Secondary audience: a reviewer of this repository evaluating how
static analysis tooling should be engineered - the false-positive discipline and the three-format
extraction without code execution are the point.

## Core features (prioritized)

1. **SQL migration linting with stable rule codes** (highest priority). Raw `.sql` migration
   files are parsed with sqlglot, statement by statement, and checked against the rule catalog.
   Each finding carries code, severity, file, line, the statement excerpt, a plain-language
   explanation, and the safe alternative.

2. **Dialect- and version-aware rule catalog** (highest priority). Nine rules, MG001-MG009,
   covering table-rewriting and lock-taking ALTERs, non-concurrent index creation, NOT NULL
   columns without a default or backfill, destructive drops, renames that break the deploy
   window, eagerly validated foreign keys, unique constraints without a concurrent index first,
   enum value removal, and DDL/DML mixing on MySQL. Rules are gated by the configured dialect and
   `postgres_version` so each fires only where the danger is real.

3. **False-positive discipline** (highest priority). The safe form of every flagged operation
   is recognized and not flagged: `NOT NULL DEFAULT` on Postgres 11+ is metadata-only, a table
   created in the same file is exempt (no traffic yet), varchar widening is exempt from the
   rewrite rule, `UNIQUE USING INDEX` is the safe MG007 form, and `CHECK ... NOT VALID` plus
   `VALIDATE` suppresses `SET NOT NULL` on 12+. A linter that cries wolf gets uninstalled.

4. **Laravel and Django extraction.** Laravel migration PHP is mined for schema builder calls
   (`Schema::create/table/drop/rename`, column and index methods, `DB::statement` raw SQL) by
   bounded regexes; Django migration Python is parsed with the `ast` module and the `operations`
   list is introspected. Both normalize to the same internal operation model the SQL path uses,
   so every rule works identically across all three formats. No scanned file is ever imported,
   evaluated, or executed.

5. **Config and allowlists with required justification.** `.migrateguard.toml` sets dialect,
   `postgres_version`, scan paths, ignored rules, and `fail_on`. Findings can be waived per site
   with an inline allow comment carrying a mandatory reason, or per file in the config allowlist,
   also with a mandatory reason. MG004 (drops) can only ever be waived inline, never ignored
   globally.

6. **Diff-base adoption mode.** `--diff-base <ref>` lints only migration files added or changed
   since the merge base with `<ref>` (via `git diff`), so a repo with years of history gets a
   clean first run and only new work is gated.

7. **Three output formats and CI exit codes.** `text` for humans (grouped by file, verdict line
   last), `json` for tooling (stable schema, deterministic ordering), `github` for inline PR
   annotations. Exit 0 clean, 1 when findings meet the failure threshold, 2 on usage or
   configuration errors.

8. **GitHub Action.** A composite action installs a pinned migrate-guard version and runs
   `check` with `--format github` and a PR-appropriate `--diff-base` default, so annotations
   appear on the changed lines of the PR.

## Non-goals

- Runtime database inspection: no connections, no catalog queries, no table-size awareness.
  migrate-guard reasons only about the migration text.
- Auto-fixing migrations; the safe alternative is explained, never applied.
- Schema diffing between environments or against a live schema.
- Dialects beyond Postgres and MySQL (SQLite-only dev migrations are out of scope).
- Generating or executing migrations; migrate-guard is read-only by design.
- ORM coverage beyond the Laravel schema builder and Django migration operations (no Alembic,
  Rails, or Prisma in this build). Estimating whether a table is actually large is also out:
  every table is assumed hot, and the allow mechanism covers the ones that are not.

## Success criteria per core feature

- **SQL linting** - A fixture file containing each unsafe form yields exactly the expected
  findings with correct file, line, code, and severity; a fixture of safe equivalents yields
  zero. A syntax error in one statement produces an MG000 diagnostic, not a crash, and does not
  stop the rest of the file.
- **Rule catalog** - Every rule fires on its documented unsafe forms and stays silent on its
  documented safe forms for both dialects, verified by a per-rule test matrix. Postgres-only
  rules never fire under `dialect = "mysql"` and vice versa.
- **False-positive discipline** - `ADD COLUMN ... NOT NULL DEFAULT` with `postgres_version = 16`
  produces no finding; the same statement with `postgres_version = 10` produces MG001. Every
  operation inside a `CREATE TABLE` in the same file produces no finding.
- **Laravel and Django extraction** - Equivalent dangerous changes written as raw SQL, Laravel
  PHP, and Django operations yield the same rule codes. A booby-trapped migration file whose
  import or execution would create a sentinel file is scanned with no side effects.
- **Config and allowlists** - An inline allow with a reason suppresses exactly one finding and is
  reported as allowed with its reason; an allow without a reason aborts the run with exit 2; an
  ignored rule produces no findings; `ignore = ["MG004"]` is rejected at config load.
- **Diff-base mode** - With `--diff-base origin/main`, only migration files added or modified
  since the merge base are linted; an unchanged historical file with violations produces nothing,
  the same file touched in the branch produces its findings.
- **Formats and exit codes** - The same run emits equivalent findings in all three formats; JSON
  matches the documented schema; `github` lines follow the workflow-command syntax. Exit codes:
  0 on clean and allowed-only runs, 1 on gating findings, 2 on bad config or git failures.
- **GitHub Action** - On a PR adding one unsafe migration, the action run fails and the finding
  appears as an inline annotation on the right file and line; a PR touching no migrations passes
  without linting history.
