# API Contracts - migrate-guard

migrate-guard's public surfaces are the CLI (commands, flags, output formats, exit codes), the
config file, the inline allow comment grammar, and the GitHub Action inputs. All are agreed
here before any code is written; CI pipelines in user repositories depend on their stability.

## Global conventions

- Findings and reports go to **stdout**; errors, warnings, and anything human-only go to
  **stderr**. On exit 2 stdout is empty.
- **Exit codes** (frozen): `0` no gating findings (clean, allowed-only, or empty file set),
  `1` at least one non-allowed finding at or above `fail_on`, `2` configuration, usage, or
  environment error.
- **Error format** (the single consistent format, stderr, exit 2):

```
error: <one clear sentence naming the problem and its location>
<optional single remedy line>
```

Examples:

```
error: unknown key "ignroe" in .migrateguard.toml (line 4); accepted keys: dialect, postgres_version, paths, ignore, fail_on, allow
error: allow comment at db/migrations/0044_drop.sql:2 has no reason
add reason="..." with a short justification to the allow comment
error: MG004 cannot be ignored globally; use an inline allow with a reason at the drop site
```

---

## migrate-guard check

```
migrate-guard check [PATHS]... [OPTIONS]
```

Lints migration files and reports findings. PATHS (files or directories) override the
configured `paths`; at least one of the two must be present.

| Option | Default | Meaning |
|---|---|---|
| `--config PATH` | `./.migrateguard.toml` | Config file; explicit path must exist |
| `--dialect [postgres\|mysql]` | from config | Overrides config; required somewhere |
| `--postgres-version N` | from config (16) | Major version for MG001/MG003 semantics |
| `--format [text\|json\|github]` | `text` | Output format |
| `--diff-base REF` | off | Lint only files changed since `merge-base(REF, HEAD)` |
| `--fail-on [error\|warning]` | from config (`error`) | Gating threshold |
| `--no-color` | off | Force plain output (same as `NO_COLOR`) |

### Invocation examples

```
$ migrate-guard check db/migrations --dialect postgres
db/migrations/0042_add_email_index.sql
  7  MG002  error    CREATE INDEX without CONCURRENTLY blocks all writes to
                     users for the duration of the build.
                     statement: CREATE INDEX users_email_idx ON users (email)
                     fix: CREATE INDEX CONCURRENTLY users_email_idx ON users (email);
                          run it outside a transaction.

checked 12 files, 41 statements
1 finding: 1 error (1 gating), 0 warnings, 0 allowed
verdict: FAIL (fail_on = error)
$ echo $?
1
```

```
$ migrate-guard check db/migrations --diff-base origin/main
no migration files to check
verdict: PASS (fail_on = error)
$ echo $?
0
```

Full text-format layout, color rules, and the allowed-finding rendering are specified in
`docs/design.md`.

### JSON output (`--format json`)

One document on stdout. Schema (all keys always present, fixed order, findings sorted by
file, line, code):

```json
{
  "migrate_guard_version": "1.0.0",
  "schema_version": 1,
  "dialect": "postgres",
  "postgres_version": 16,
  "fail_on": "error",
  "files_checked": 12,
  "statements_checked": 41,
  "findings": [
    {
      "code": "MG002",
      "severity": "error",
      "file": "db/migrations/0042_add_email_index.sql",
      "line": 7,
      "table": "users",
      "message": "CREATE INDEX without CONCURRENTLY blocks all writes to users for the duration of the build.",
      "safe_alternative": "CREATE INDEX CONCURRENTLY users_email_idx ON users (email); run it outside a transaction.",
      "statement": "CREATE INDEX users_email_idx ON users (email)",
      "allowed": false,
      "allow_reason": null
    }
  ],
  "summary": { "error": 1, "warning": 0, "allowed": 0, "gating": 1 },
  "verdict": "fail"
}
```

- `schema_version` bumps only on breaking schema changes (major release).
- `table` and `allow_reason` are `null` when not applicable; keys are never omitted.
- `verdict` is `"pass"` or `"fail"` and always agrees with the exit code (`fail` iff exit 1).

### GitHub annotations output (`--format github`)

One workflow-command line per finding, then the plain-text summary for the job log:

```
::error file=db/migrations/0042_add_email_index.sql,line=7,title=MG002::CREATE INDEX without CONCURRENTLY blocks all writes to users for the duration of the build. Safe alternative: CREATE INDEX CONCURRENTLY users_email_idx ON users (email); run it outside a transaction.
::warning file=db/migrations/0045_enum.sql,line=3,title=MG008::Enum redefinition may remove or reorder members, which copies the table and can corrupt values.
::notice file=db/migrations/0043_cleanup.sql,line=3,title=MG004 (allowed)::DROP TABLE audit_legacy allowed: retired 2026-06, approved OPS-1123
checked 12 files, 41 statements
2 findings: 1 error (1 gating), 1 warning, 1 allowed
verdict: FAIL (fail_on = error)
```

Severity mapping: `error` findings emit `::error`, `warning` findings emit `::warning`,
allowed findings emit `::notice` with the justification. Message text has newlines collapsed
to spaces (workflow commands are single-line).

---

## migrate-guard rules

```
$ migrate-guard rules
MG000  warning  postgres,mysql  statement or file that could not be analyzed
MG001  error    postgres,mysql  ALTER that rewrites or scan-locks the table
MG002  error    postgres        CREATE INDEX without CONCURRENTLY
MG003  error    postgres,mysql  NOT NULL column added without default or backfill
MG004  error    postgres,mysql  DROP COLUMN / DROP TABLE (inline allow required)
MG005  error    postgres,mysql  column or table rename breaks the deploy window
MG006  error    postgres        foreign key added with immediate validation
MG007  error    postgres        UNIQUE constraint without a concurrent index first
MG008  warning  postgres,mysql  enum value removal or redefinition
MG009  warning  mysql           DDL and DML mixed in one migration
```

Exit 0 always. No options.

## migrate-guard explain

```
migrate-guard explain CODE
```

Prints the rule's full explanation: what it detects, why the operation is dangerous (named
locks, rewrite and scan behavior, version specifics), an unsafe example, the safe alternative
as runnable statements, and how to suppress it with an inline allow. Exit 0; unknown code
exits 2 with `error: unknown rule code "MG999"; run migrate-guard rules for the list`.

## migrate-guard --version / --help

`--version` prints `migrate-guard <semver>` and exits 0. Every command supports `--help` with
defaults and accepted values stated.

---

## Config file contract (.migrateguard.toml)

```toml
[migrate-guard]
dialect = "postgres"          # required here or via --dialect: postgres | mysql
postgres_version = 16         # optional, default 16
paths = ["db/migrations"]     # required here or via CLI PATHS
ignore = ["MG009"]            # optional; MG004 and MG000 are rejected here
fail_on = "error"             # optional: error | warning

[[migrate-guard.allow]]
file = "db/migrations/0043_cleanup.sql"
rules = ["MG004"]
reason = "audit_legacy retired 2026-06, approved OPS-1123"
```

Validation rules (violations are exit 2):

- Unknown keys anywhere are errors, with the offending key and the accepted list named.
- `dialect` must be `postgres` or `mysql`; `postgres_version` a positive integer;
  `fail_on` one of `error`/`warning`; `ignore` entries must match existing rule codes.
- `ignore` may not contain `MG004` (drops need per-site justification) or `MG000`
  (parse failures must stay visible).
- Every `[[allow]]` entry needs `file` (string), `rules` (non-empty list of valid codes), and
  `reason` (non-empty after trimming whitespace).
- CLI flags override config values; PATHS on the command line override `paths` entirely.

## Inline allow comment contract

Grammar (identical across comment styles; `--` SQL, `//` PHP, `#` Python):

```
<comment-marker> migrate-guard: allow CODE[,CODE...] reason="<non-empty justification>"
```

Examples:

```sql
-- migrate-guard: allow MG004 reason="audit_legacy retired 2026-06, approved OPS-1123"
DROP TABLE audit_legacy;
```

```php
// migrate-guard: allow MG005 reason="rename coordinated with blue-green cutover OPS-1201"
$table->renameColumn('email', 'primary_email');
```

```python
# migrate-guard: allow MG004,MG008 reason="status enum and column removed together, OPS-991"
```

Semantics:

- Applies to findings with a listed code raised by the first flaggable operation at or after
  the comment's line in the same file.
- The finding is still reported, marked allowed with the reason, and never gates.
- Malformed allow (missing/empty reason, unknown code, unparseable line) aborts the run with
  exit 2 naming file and line. An allow that matches no finding prints a stderr warning.

---

## GitHub Action contract (action.yml)

Composite action; wraps the CLI. Usage:

```yaml
- uses: thealirazadev/migrate-guard@v1
  with:
    paths: db/migrations
    diff-base: origin/${{ github.base_ref }}
```

| Input | Default | Meaning |
|---|---|---|
| `paths` | (config) | Space-separated paths passed to `check` |
| `config` | `.migrateguard.toml` | Config file path |
| `diff-base` | base branch on PRs, empty otherwise | Passed as `--diff-base` when non-empty |
| `fail-on` | (config) | Passed as `--fail-on` when set |
| `format` | `github` | Output format |
| `version` | pinned in the action | migrate-guard version to `pip install` |

Behavior: installs Python 3.12 and `migrate-guard==<version>`, runs `check`, and lets the
CLI exit code fail or pass the step. On `pull_request` events the default `diff-base` is the
PR base branch, so only the PR's migration changes are linted; on other events the default is
a full run. Annotations appear inline because the default format is `github`.

## Stability policy

- Exit codes, the JSON schema (per `schema_version`), rule codes, default severities, and this
  allow grammar are frozen within a major version.
- New rules, severity changes, or grammar extensions ship only in a major release and are
  listed in the changelog, because they change CI outcomes in user repositories.
