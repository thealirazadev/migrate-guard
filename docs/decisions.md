# Design decisions

The engineering decisions behind migrate-guard that the current code reflects, with the reason
for each and the bugs or edge cases that shaped them. The full rule catalog and data model are in
`docs/architecture.md`; the CLI contract is in `docs/api-contracts.md`.

## 1. One intermediate representation for every input format

The SQL, Laravel and Django extractors all normalize into the same frozen `Operation` dataclass
(`ir.py`), and the rules only ever see operations. Each rule is written once and behaves the same
whether the change came from a `.sql` file, a Laravel schema builder call or a Django operation.
Per-format rules would triple the rule surface and guarantee drift between formats.
`tests/test_parity.py` pins this: the same `DROP COLUMN` written three ways yields the same
codes.

## 2. Scanned files are parsed, never executed

Migration files come from arbitrary repositories, so they are treated as hostile input. SQL is
parsed with sqlglot, Django files with Python's `ast` module, and Laravel files with regexes over
the source text. Nothing is imported, evaluated or shelled. Django `RunPython` operations are
skipped because they cannot be analyzed without running them. Booby-trapped fixtures (a Django
migration with a module-level side effect, a PHP file with `eval` and backtick constructs) are
scanned by tests that assert nothing happened.

## 3. The new-table exemption lives in the engine

`engine.check_file()` collects every table created in the file and skips all operations on those
tables before any rule runs. A table created in the same migration has no rows and no traffic, so
nothing done to it can lock or rewrite anything that matters. Putting this in one place removes
the largest class of false positives and keeps each rule module focused on its own semantics.

## 4. Statements are split on sqlglot tokens, not on `;`

The SQL extractor tokenizes the file once and groups tokens between semicolon tokens. Each token
carries its source line, so every finding reports the true first line of its statement in a
multi-statement file, and a semicolon inside a string literal or comment cannot split a
statement. `extract()` takes the dialect as an argument because sqlglot cannot tokenize or parse
without one (MySQL backticks versus Postgres quoting), and keeping config reads out of the
extractors keeps them pure.

## 5. Content problems are findings, environment problems are exit 2

Anything wrong inside a scanned file becomes an MG000 finding and the run continues; anything
wrong with config, paths, file encoding or permissions raises `MigrateGuardError` and exits 2
with a one-line `error:` message and an empty stdout. A partial report after an environment error
would be worse than none. Bugs found while hardening this line:

- A deeply nested expression raised `RecursionError` out of `sqlglot.parse_one`, which escaped the
  extractor and aborted the whole run with an internal error. Extraction now catches
  `SqlglotError` and `RecursionError` per statement (and around tokenization), while genuine
  coding errors such as `AttributeError` still surface.
- sqlglot keeps ALTER forms it does not model as a generic `Command`. Treating every `Command` as
  "no operation" swallowed multi-action ALTERs, so
  `ALTER TABLE users ADD COLUMN a int, DROP COLUMN legacy_flag;` reported a clean file and hid a
  drop. An unmapped `ALTER TABLE` now produces MG000; other `Command` statements (`SET`,
  `VACUUM`, `ALTER SEQUENCE`) stay silent so valid SQL does not drown in noise.
- Two safe Postgres forms that sqlglot leaves as a `Command`, `VALIDATE CONSTRAINT` and
  `ADD CONSTRAINT ... UNIQUE USING INDEX`, are recovered with two anchored, length-bounded
  regexes, because MG001 and MG007 must recognize them to stay silent on the documented safe
  sequences.

## 6. Dangerous-by-default when the safe case cannot be proven

When a single file cannot prove an operation is safe, it is reported. The failure direction of a
missed table rewrite is an outage; the failure direction of a false positive is one finding a
reviewer has to look at and dismiss.

- A SQL file never states a column's previous type, so every `ALTER COLUMN ... TYPE` is MG001,
  and Django `AlterField` is treated the same way. `migrate-guard explain MG001` states this
  limitation, including the widenings Postgres does in place.
- An `ADD COLUMN ... DEFAULT` counts as a constant default only when its whole expression tree is
  literals, booleans, nulls, negation, parentheses, casts, arrays and tuples. Anything with a
  function call or subquery is treated as volatile. Listing volatile functions instead would
  silently pass every function the list missed. One consequence: `DEFAULT now()` is reported on
  PostgreSQL 11+ even though Postgres classifies `now()` as stable and treats it as metadata-only.
- A MySQL `CHANGE` that renames a column emits both `rename_column` and a type change, so it
  reports MG005 and MG001: the statement really is a rename and a full table copy.

## 7. Version- and dialect-aware rules

`postgres_version` (default 16, overridable with `--postgres-version`) decides what MG001 means:
`ADD COLUMN ... NOT NULL DEFAULT <constant>` is a rewrite on 10 and metadata-only from 11, and
`SET NOT NULL` is exempt on 12+ only when the same file adds a `CHECK (col IS NOT NULL) NOT
VALID` and validates that same constraint by name. Matching the validation by constraint name,
not by table, stops an unrelated `VALIDATE CONSTRAINT` from suppressing the finding. Each rule
declares the dialects it applies to, so MG009 (implicit commits around DDL) only runs on MySQL.

## 8. MG009 reports once per file and ignores seed rows

Mixing DDL and DML is a problem of the file's shape, so MG009 reports once, at the first data
statement. Bug found: when that first statement seeded a table created in the same file, the
engine exempted it while the rule still counted it, so a later backfill on a live table went
unreported. The rule now skips data statements on tables created in the file when picking the
statement to report.

## 9. Laravel: bounded regexes over stripped source, `up()` only

Laravel files are matched with bounded regexes after PHP comments and string contents are
blanked out (offsets and newlines preserved, so line numbers stay right), which avoids a PHP
parser dependency and means SQL inside a comment cannot produce findings. `DB::statement` and
`DB::unprepared` literals are handed to the SQL extractor; a non-literal argument is MG000 rather
than a guess. Bug found by running against real projects: every create-table migration reported
MG004 because `Schema::dropIfExists` in `down()` was linted. Only `up()` runs on deploy, so the
extractor now blanks everything outside `up()`; files without an `up()` are scanned whole.

## 10. Django: default table names and the `atomic` check

Django operations name a model, not a table, so the extractor derives Django's default
`<app_label>_<model>` table from the migrations folder's parent and carries the field name.
Without this, messages said "the table" and the new-table exemption never matched, which produced
a false MG007 on an `AlterUniqueTogether` for a model created in the same file. An
`AddIndexConcurrently` in a migration that does not set `atomic = False` gets MG002 with a message
explaining that Postgres refuses `CONCURRENTLY` inside a transaction, and that the fix is
`atomic = False`. Discovery skips `migrations/__init__.py` package markers, which otherwise each
produced an MG000.

## 11. Drops and diagnostics cannot be ignored globally

The config loader rejects `MG004` and `MG000` in the `ignore` list with exit 2. A global ignore
of destructive drops or of "this statement was not checked" silently rots, so the error message
points at a per-site waiver next to the offending statement instead. The loader validates the whole config schema
strictly, including unknown keys and `[[allow]]` entries without a reason, so a typo never turns
into a silently ignored setting.

## 12. Deterministic, terminal-independent output

Findings are sorted by file, line and rule code, discovery sorts directories and files, and the
text reporter wraps message and fix lines at 80 columns without breaking words, while statement
excerpts are capped at 200 characters and never wrapped. Two runs over the same tree are
byte-identical, which the golden-file test relies on. sqlglot's logger is set to `ERROR` at
startup because it warns on every `Command` fallback, and stderr is reserved for migrate-guard's
own messages.

## 13. Allows are applied after the rules, never inside them

The `ignore` list, inline allows and config allows were validated from the start but not applied,
so a documented waiver still failed the build. They are now resolved in `allows.py` after the
engine runs: ignored codes are dropped, then each inline allow marks the findings with a listed
code on the first operation at or after its line, then config allows mark their codes across
their file. An allowed finding stays in the report with its reason and never gates. Inline
allows are parsed line by line from the source text, so they work the same for all three
formats and nothing is evaluated. A malformed allow (no or empty reason, an unknown code, an
unparseable `migrate-guard:` comment) is exit 2 naming file and line, and an allow that matches
nothing is a stderr warning, because a stale waiver is a silent hole waiting to be reused. Rule
codes in `ignore`, config allows and inline allows must be codes that exist, not just
`MG` plus three digits, so a typo such as `MG010` is rejected instead of doing nothing.
