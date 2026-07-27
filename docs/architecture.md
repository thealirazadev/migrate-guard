# Architecture - migrate-guard

## App flow

```
migrate-guard check [PATHS] [--diff-base REF] [--format text|json|github]
        │
        ▼
Config loader (.migrateguard.toml + CLI overrides)
        └─ unknown key / bad value / missing dialect → exit 2, one-line error
        ▼
Discovery
        ├─ explicit PATHS or configured paths; format by extension
        │  (.sql → sql, .php → laravel, .py → django)
        └─ --diff-base REF: intersect with `git diff --name-only` vs merge base
        ▼
Extractors (one per format; none ever executes scanned content)
        ├─ sql:     sqlglot.parse per statement → Operation list
        ├─ laravel: bounded regexes over schema builder calls;
        │           DB::statement literals re-routed through the sql extractor
        ├─ django:  ast.parse, walk Migration.operations;
        │           RunSQL literals re-routed through the sql extractor
        └─ unparseable statement / call → MG000 diagnostic, file continues
        ▼
Rule engine
        ├─ per file: collect tables created here (new-table exemption)
        └─ per operation, in file order: run every dialect-applicable rule;
           rules may look back at earlier ops in the same file
        ▼
Suppression resolution
        ├─ config ignore drops findings (MG004 refuses to be ignored)
        └─ inline / config allow with required reason → kept, marked allowed;
           malformed allow (no reason, unknown code) → exit 2
        ▼
Reporter (text | json | github) → stdout, deterministic order (file, line, code)
Exit: 0 clean or allowed-only · 1 findings at/above fail_on · 2 usage/config error
```

## Tech stack with rationale

- **Python 3.12** - `tomllib` in the standard library (no TOML dependency), modern `ast`, broad
  CI availability. 3.12 is the floor and the pin in CI.
- **sqlglot (pinned exact)** - The only credible pure-Python SQL parser with real Postgres and
  MySQL dialects. Parsing only, never transpiling; the AST gives statement type, table, columns,
  and constraint details with token positions for line numbers. Trade-off: sqlglot is permissive
  by design, so rule detection keys off AST node shape, not parse success.
- **Click (pinned exact)** - Command groups, flag parsing, `--help` text, testability via
  `CliRunner`. The CLI surface is small; Click keeps it declarative.
- **pytest + ruff + black (dev)** - House Python toolchain; tests run with zero network access.
- **uv with pyproject.toml** - Dependencies and committed `uv.lock`, exact pins per workspace
  rules. Build backend hatchling (src layout with zero config).
- **No PHP parser dependency** - Laravel extraction is regex-assisted by design: a real PHP
  parser is a heavy dependency for reading one framework's fluent builder calls. The regexes
  are bounded, documented, and tested against real-world migration fixtures; whatever they
  cannot recognize is skipped or reported as MG000, never guessed.

Runtime dependencies: sqlglot and click. Everything else is standard library.

## System components

- **`cli.py`** - Click group with `check`, `rules`, and `explain`: flags, config loading,
  pipeline orchestration, exit-code mapping. No analysis logic.
- **`config.py`** - Loads `.migrateguard.toml`, validates strictly (unknown keys are errors,
  enums checked, allow entries need a non-empty reason), merges CLI overrides into one frozen
  `Config`.
- **`discovery.py`** - Resolves paths to migration files, classifies format by extension,
  implements diff-base filtering via `git merge-base REF HEAD` plus `git diff --name-only`;
  git failures become exit-2 errors carrying the git stderr line.
- **`extractors/`** - `sql.py`, `laravel.py`, `django.py`, each implementing
  `extract(path, text) -> ExtractionResult` (operations + allows + diagnostics). The only
  layer that knows about file formats; rules never see format-specific detail.
- **`ir.py`** - `Operation`, `Allow`, `Finding`, `SourceSpan`, the `OpKind` enum. Frozen
  dataclasses; the contract between extractors, engine, and reporters.
- **`engine.py`** - Runs registered rules over each file's operation list, applies the
  new-table exemption, then resolves ignores and allows into the final finding list.
- **`rules/`** - One module per rule plus `base.py` (the `Rule` protocol and registry); each
  module owns its detection logic, message, safe-alternative text, and the `explain` long form.
- **`reporters/`** - `text.py`, `json.py`, `github.py`; pure result-to-stdout functions, per `docs/design.md`.
- **`action.yml`** (repo root) - Composite GitHub Action: setup-python, `pip install
  migrate-guard==<version>`, run `check` with `--format github` and a PR-aware diff base.

## Data model

migrate-guard has no database (runtime inspection is a non-goal); the data model is the frozen
dataclasses in `ir.py` plus the config schema, and the coding agent must not rename fields.
`SourceSpan` is `(file: str, line: int)` - the path as given, 1-based first line of the
statement or call.

### Operation
| Field | Type | Notes |
|---|---|---|
| kind | OpKind | see enum below |
| table | str \| None | normalized: identifier quotes stripped, case preserved |
| column | str \| None | for column-level operations |
| details | dict | kind-specific keys, listed per kind below |
| span | SourceSpan | |
| raw | str | statement or call excerpt, single line, capped at 200 chars |

`OpKind` values and their `details` keys:

| kind | details | produced by |
|---|---|---|
| `create_table` | - | CREATE TABLE, `Schema::create`, `CreateModel` |
| `add_column` | `type`, `not_null` bool, `has_default` bool, `default_volatile` bool | ADD COLUMN, builder column methods, `AddField` |
| `alter_column_type` | `new_type`, `old_type` (None when unknowable) | ALTER COLUMN TYPE, MODIFY/CHANGE, `->change()`, `AlterField` |
| `set_not_null` | - | SET NOT NULL, `AlterField(null=False)`, `->nullable(false)->change()` |
| `add_check_not_valid` | `column` guessed from `IS NOT NULL` body, else None | ADD CONSTRAINT CHECK ... NOT VALID |
| `validate_constraint` | `constraint` | VALIDATE CONSTRAINT |
| `drop_column` | - | DROP COLUMN, `dropColumn`, `RemoveField` |
| `drop_table` | - | DROP TABLE, `Schema::drop[IfExists]`, `DeleteModel` |
| `rename_column` | `new_name` | RENAME COLUMN, CHANGE with new name, `renameColumn`, `RenameField` |
| `rename_table` | `new_name` | RENAME TO, `Schema::rename`, `RenameModel` |
| `create_index` | `unique` bool, `concurrent` bool | CREATE [UNIQUE] INDEX, `->index()`, `AddIndex`, `AddIndexConcurrently` |
| `add_foreign_key` | `not_valid` bool | ADD CONSTRAINT FOREIGN KEY, `->foreign()`, `constrained()` |
| `add_unique_constraint` | `using_index` bool | ADD CONSTRAINT UNIQUE [USING INDEX], `AddConstraint(UniqueConstraint)` |
| `drop_type` | - | DROP TYPE (Postgres) |
| `redefine_enum` | - | MODIFY/CHANGE to ENUM(...) (MySQL), `->enum()->change()` |
| `dml` | `verb` (`insert`/`update`/`delete`) | raw DML statements |
| `other_ddl` | `statement_type` | recognized DDL not covered above |

### Allow
`Allow(codes: tuple[str, ...], reason: str, span: SourceSpan, source: str)` - the rule codes it
waives, the mandatory non-empty justification, where the comment sits (config allows use line
0), and `inline` or `config`. An inline allow applies to findings raised by the next operation
at or after its line in the same file; a config allow applies to the named file and codes as a
whole.

### Finding
| Field | Type | Notes |
|---|---|---|
| code | str | `MG000`-`MG009` |
| severity | str | `error` or `warning` (post-config, per the catalog defaults) |
| span | SourceSpan | |
| table | str \| None | |
| message | str | one sentence naming the operation and the danger |
| safe_alternative | str | one or two sentences; concrete statements, not platitudes |
| statement | str | the `Operation.raw` excerpt |
| allowed | bool | True when waived by an allow |
| allow_reason | str \| None | the justification, echoed in every reporter |

### Config (`.migrateguard.toml`, all keys top-level under `[migrate-guard]`)
| Key | Type | Default | Notes |
|---|---|---|---|
| dialect | str | required | `postgres` or `mysql`; CLI `--dialect` overrides |
| postgres_version | int | 16 | major version; drives MG001/MG003 semantics |
| paths | list[str] | [] | scan roots; required unless PATHS given on the CLI |
| ignore | list[str] | [] | rule codes reported never; `MG004` and `MG000` rejected here |
| fail_on | str | `error` | `error` or `warning`; the gating threshold |
| [[allow]] | table array | [] | `file`, `rules` (list), `reason` (required non-empty) |

Unknown keys anywhere in the file are exit-2 errors: a misspelled `ignore` must fail loudly.

## Rule catalog

Severities are defaults; dialect gates are hard (a rule never fires outside its dialects), and
the new-table exemption below applies to every rule.

| Code | Severity | Dialects | Fires on |
|---|---|---|---|
| MG000 | warning | both | statement or call that could not be parsed or extracted |
| MG001 | error | both | ALTER that rewrites or scan-locks the table |
| MG002 | error | postgres | CREATE INDEX without CONCURRENTLY |
| MG003 | error | both | ADD COLUMN NOT NULL without default or backfill |
| MG004 | error | both | DROP COLUMN or DROP TABLE (inline allow required) |
| MG005 | error | both | renaming a column or table |
| MG006 | error | postgres | foreign key added with immediate validation |
| MG007 | error | postgres | UNIQUE constraint without a concurrent index first |
| MG008 | warning | both | enum value removal or redefinition |
| MG009 | warning | mysql | DDL and DML mixed in one migration |

Per-rule detection and suppression detail:

- **MG001** (rewrite/lock). Postgres triggers: (a) `alter_column_type` outside the
  safe-widening list (varchar(n) to larger varchar or text, numeric(p,s) to higher precision
  same scale, varbit widening) - everything else, including any change with unknown old type,
  rewrites under ACCESS EXCLUSIVE; (b) `add_column` with a default on `postgres_version < 11`
  (whole-table rewrite; on 11+ a non-volatile default is metadata-only and must not fire, while
  a volatile default such as `now()` still rewrites and fires); (c) `set_not_null`, which takes
  ACCESS EXCLUSIVE and scans the table - suppressed when `postgres_version >= 12` and an
  earlier op in the same file added and validated a `CHECK (col IS NOT NULL) NOT VALID`
  (Postgres then skips the scan). MySQL trigger: `alter_column_type` unless the change is
  varchar widening within the same length-byte class; all other type changes copy the table.
- **MG002** (non-concurrent index, Postgres). `create_index` with `concurrent = False`. A plain
  CREATE INDEX takes SHARE, blocking all writes for the build. Safe alternative:
  `CREATE INDEX CONCURRENTLY`, which cannot run inside a transaction block - the message names
  the framework escape hatch (Django `atomic = False` + `AddIndexConcurrently`, Laravel
  `DB::statement` outside a transactional migration). Django `AddIndexConcurrently` counts as
  safe only when the migration sets `atomic = False`; otherwise MG002 fires with a message
  about the atomic requirement.
- **MG003** (NOT NULL without default/backfill). `add_column` with `not_null = True` and
  `has_default = False`. Fails outright on any non-empty table or forces a rewrite dance. With
  a default present there is no MG003: the Postgres pre-11 case escalates to MG001(b); the 11+
  and MySQL 8.0 cases are safe and produce nothing. Safe alternative in the message: add
  nullable, backfill in batches, then the MG001(c)-safe NOT NULL sequence.
- **MG004** (destructive drop). `drop_column` and `drop_table`. Always a finding; the only
  waivers are an inline allow at the drop site or a per-file config allow - config `ignore`
  refuses `MG004` at load time. Destruction must carry a written justification next to the
  destruction.
- **MG005** (rename). `rename_column` and `rename_table`. The old name disappears while the
  previous application version is still serving traffic. Safe alternative: expand-contract -
  add the new name, dual-write, backfill, switch reads, drop the old name later under an MG004
  allow.
- **MG006** (eager FK validation, Postgres). `add_foreign_key` with `not_valid = False`. The
  immediate validation scans the referencing table and locks both tables. Safe:
  `ADD CONSTRAINT ... NOT VALID` now, `VALIDATE CONSTRAINT` in a later migration (SHARE UPDATE
  EXCLUSIVE, write-friendly). A `validate_constraint` op alone never fires anything.
- **MG007** (unique constraint, Postgres). `add_unique_constraint` with `using_index = False`
  builds its index under ACCESS EXCLUSIVE. Safe: `CREATE UNIQUE INDEX CONCURRENTLY` first,
  then `ADD CONSTRAINT ... UNIQUE USING INDEX idx`; the `using_index = True` form never fires.
- **MG008** (enum removal). MySQL: `redefine_enum` - the previous member list is unknowable
  without the old schema (schema diffing is a non-goal), and a removal or reorder copies the
  table and can corrupt values, so every enum redefinition is flagged warning for human review.
  Postgres: `drop_type`, the recreate-the-type pattern. The message states the heuristic
  honestly.
- **MG009** (DDL/DML mix, MySQL). Fires once per file containing at least one DDL and one
  `dml` operation. MySQL DDL implicitly commits, so the file is not atomic no matter what the
  framework wraps it in: a mid-file failure leaves partial state a rerun may not survive.
  Safe alternative: separate schema migrations from batched backfill migrations.

### New-table exemption (engine-wide)

Before rules run, the engine collects every table with a `create_table` op in the current file;
any operation targeting one of those tables is exempt from every rule. A table created in this
migration has no rows and no traffic, so nothing can lock or rewrite anything that matters.
This single check kills the largest class of false positives: building a new table with NOT
NULL columns, indexes, and foreign keys in one file is the normal, safe pattern.

## Key flows

### check run, step by step

1. Load config; apply CLI overrides; exit 2 on any validation failure.
2. Discover files: CLI PATHS if given, else `paths` from config (neither: exit 2). Classify
   format by extension; unreadable files are exit-2 errors, not lint results.
3. With `--diff-base`: resolve `git merge-base REF HEAD`, run `git diff --name-only
   --diff-filter=ACMR` across that range, intersect with the discovered set. Any git failure
   is exit 2 with git's own message; deleted files never appear.
4. Extract each file to operations, allows, and MG000 diagnostics. Extraction never raises to
   the top: an internal sqlglot error on one statement becomes MG000 at that line and the rest
   of the file continues.
5. Engine: per file, build the new-table set, run each dialect-applicable rule per operation in
   file order (rules receive the operation list and index for same-file lookback).
6. Suppression: drop findings whose code is in `ignore`; match the rest against allows (inline
   first, then config); matches get `allowed = True` plus the reason. An allow matching nothing
   prints a stderr warning (stale allows rot).
7. Report on stdout in the selected format, sorted by (file, line, code). Diagnostics never
   print to stdout - stdout belongs to the report.
8. Exit 1 if any finding with `allowed = False` is at or above `fail_on`, else 0.

### Allow resolution

Inline allow grammar (comment styles per format; grammar identical):

```
-- migrate-guard: allow MG004 reason="users_legacy retired 2026-06, approved OPS-1123"
#  migrate-guard: allow MG005 reason="rename coordinated with blue-green cutover"
// migrate-guard: allow MG004,MG008 reason="table and enum removed together, OPS-991"
```

- Codes: one or more, comma-separated, each matching `MG\d{3}`.
- `reason="..."` is mandatory; an empty or missing reason, an unknown code, or an unparseable
  allow line is exit 2 naming file and line. A suppression that cannot be trusted must never
  half-work.
- Scope: the allow waives matching findings from the first operation at or after the comment's
  line; one allow waives one operation's findings per code (no blanket file waivers inline -
  that is what config allows are for).

### Diff-base mode invariants

- Narrows the file set only; never changes rule behavior, severities, or config. A full run
  without `--diff-base` over the same tree is always the superset. Merge-base, not the ref
  itself, so a stale target branch never makes unrelated files appear changed; a
  renamed-and-modified file counts as changed (ACMR on the new path).

## Failure modes

| Failure | Handling |
|---|---|
| Missing config with explicit `--config`; no config and no PATHS; unknown key / bad enum / bad type | exit 2, offending path or key and accepted values named |
| Allow entry or inline allow without reason | exit 2, file and line named |
| `ignore` containing MG004 or MG000 | exit 2 (drops must be per-site; parse failures must stay visible) |
| Unreadable or undecodable file (permissions, binary) | exit 2; environment problem, not a lint result |
| Statement sqlglot cannot parse | MG000 warning at that line; rest of file continues |
| Laravel call the regexes cannot classify | skipped silently when harmless (unknown fluent method); MG000 when a schema-changing call is recognized but its arguments are not extractable |
| `DB::statement` / `RunSQL` with a non-literal argument; Django file without a `Migration` class or `operations` list | MG000 (cannot analyze what is not there) |
| git absent / not a repo / unknown ref with `--diff-base` | exit 2 with git's stderr line |
| Zero files after discovery or diff filtering | exit 0, report states "no migration files to check" (normal in diff mode) |
| Internal bug (unexpected exception) | exit 2, one-line error to stderr; full traceback only with `MIGRATE_GUARD_DEBUG=1` |

## Correctness invariants

- **Never executes scanned content.** No `exec`, `eval`, `import`, or interpreter invocation on
  any scanned file, ever: Django via `ast.parse` only, Laravel via regexes, SQL via sqlglot.
  Enforced by a test that scans booby-trapped fixtures and asserts no side effect occurred.
  The only subprocess ever run is `git` for diff mode, fixed argument list, never via a shell.
- **Deterministic output.** Findings sorted by (file, line, code); JSON key order fixed; two
  runs over the same tree and config are byte-identical, so CI diffs of lint output mean
  something.
- **Read-only.** migrate-guard writes nothing to disk, creates no cache, touches no network.
  Concurrent runs over the same tree are safe: each is a pure function of (files, config,
  git state).
- **Exit-code stability.** 0/1/2 meanings are frozen (flow step 8); allowed findings never
  gate; warnings gate only under `fail_on = "warning"`. A rule addition or default-severity
  change alters CI behavior and therefore ships only in a major version.
- **Fail loud on suppression errors.** Anything wrong in the suppression chain (malformed
  allow, unknown code, ignored MG004) is exit 2, never a best-effort guess - a linter whose
  silencing mechanism silently misfires is worse than no linter.
- **Conservative on unknowns.** Unknown old column type is treated as a rewrite (MG001 fires);
  unanalyzable raw SQL is MG000, visible. The tool errs toward a human looking at it; allows
  are the pressure valve.

## Directory layout

```
migrate-guard/
├── README.md
├── action.yml                      # composite GitHub Action wrapping the CLI
├── pyproject.toml                  # exact pins; uv.lock committed
├── .migrateguard.toml.example
├── docs/
│   └── (this documentation set)
├── src/migrate_guard/
│   ├── __init__.py                 # __version__ only
│   ├── cli.py
│   ├── config.py
│   ├── discovery.py
│   ├── ir.py
│   ├── engine.py
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── sql.py
│   │   ├── laravel.py
│   │   └── django.py
│   ├── rules/
│   │   ├── __init__.py             # registry: code → Rule
│   │   ├── base.py                 # Rule protocol; message/explain plumbing
│   │   └── mg000.py ... mg009.py   # one module per rule; mg000 is the diagnostic constructor
│   └── reporters/
│       ├── __init__.py
│       └── text.py · json.py · github.py
└── tests/
    ├── conftest.py                 # fixture loaders, CliRunner helpers
    ├── fixtures/{sql,laravel,django}/   # unsafe/ and safe/ per dialect; boobytraps
    ├── test_config.py · test_discovery.py
    ├── test_extract_sql.py · test_extract_laravel.py · test_extract_django.py
    ├── test_engine.py              # new-table exemption, lookback, ordering
    ├── test_rules_mg001.py ... test_rules_mg009.py
    ├── test_allows.py
    ├── test_diff_base.py           # against a scratch git repo built in tmp_path
    ├── test_reporters.py           # golden files for all three formats
    └── test_cli.py                 # exit codes, flag handling, stderr contract
```

## External dependencies and environment

External runtime services: none. Required environment: Python 3.12; `git` on PATH only when
`--diff-base` is used. The only environment variables read are `MIGRATE_GUARD_DEBUG` (traceback
on internal errors) and `NO_COLOR` (see `docs/design.md`). Configuration lives in
`.migrateguard.toml` and flags - deliberately not in env vars, so CI runs reproduce from the
repo alone.
