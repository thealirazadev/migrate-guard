# Project Memory - migrate-guard

Running log of what is done, in progress, and decided. Update after every meaningful chunk of
work; log every non-obvious decision with its reason. Keep entries short and dated.

## Completed

- 2026-07-27 - Planning documentation created (README, PRD, architecture, rules, phases,
  design, testing, api-contracts, launch-checklist, memory). No code yet; docs under owner
  review. Implementation follows `docs/phases.md` starting with Phase 1 once approved.

- 2026-07-28 - Phase 1 complete: foundation and the SQL pipeline, in the thirteen commits listed
  in `docs/phases.md`. Package scaffold (src layout, hatchling, exact pins, committed `uv.lock`,
  `migrate-guard` console script), `ir.py`, config loader, discovery, sqlglot SQL extractor with
  MG000 diagnostics, engine with the rule registry and the new-table exemption, MG002, MG004,
  the text reporter, the `check` command with 0/1/2 exit codes, the CI workflow, and the test
  suite (76 tests) with SQL fixtures and one golden file.

- 2026-07-29 - Phase 2 complete: the full rule catalog with false-positive discipline. The SQL
  extractor now maps every `OpKind` in `docs/architecture.md`; MG001, MG003, MG005, MG006, MG007,
  MG008, and MG009 joined MG002 and MG004; `rules` and `explain` render the catalog; `check`
  gained `--postgres-version`. Fixtures were split into
  `tests/fixtures/sql/{postgres,mysql}/{safe,unsafe}` and every rule has both a firing fixture and
  a safe-form fixture that stays silent. Eleven commits: the ten listed in `docs/phases.md` plus
  one corrective `fix(rules)`.

- 2026-07-29 - Phase 2 functional review: three defects found and fixed, one commit each
  (`fix(extract): report unmapped alter table as mg000`,
  `fix(extract): contain every parser failure in the file that caused it`,
  `fix(rules): stop seed data silencing mg009 for the rest of the file`). Each carries a test that
  fails on the parent commit and passes on the fix. Nothing else in the Phase 2 diff needed a
  change; the rule matrix, the dialect gates, the version gates, and the new-table exemption all
  held up under probing.

## Project status

- Phases 1 and 2 shipped and verified locally; Phase 3 (Laravel and Django extractors) not
  started, awaiting owner approval.
- Verified on 2026-07-29 with Python 3.12.3 and uv 0.11.28: `uv sync`,
  `uv run python -c "import migrate_guard"`, `uv run ruff check .`, `uv run black --check .`, and
  `uv run pytest` all clean (254 passed, 265 after the three review fixes below). Observed
  against the fixture corpus: the eleven Postgres
  unsafe fixtures report exactly MG000-MG008 at the expected lines and exit 1; the eight Postgres
  safe fixtures and the five MySQL safe fixtures print "no problems found" and exit 0; the six
  MySQL unsafe fixtures report MG001, MG003, MG004, MG005, MG008, and MG009 and exit 1;
  `ADD COLUMN ... NOT NULL DEFAULT` is silent on 11, 12, and 16 and MG001 on 10, while the same
  statement without a default is MG003 on every version; the CHECK NOT VALID plus VALIDATE plus
  SET NOT NULL sequence is silent on 12 and 16 and MG001 on 10 and 11, and a bare SET NOT NULL
  still fires; `rules` prints ten rows matching `docs/api-contracts.md` byte for byte;
  `explain MG001` prints the long form and `explain MG999` exits 2; two runs over the whole
  Postgres fixture tree are byte-identical.
- CI: green on every Phase 2 push, including the phase tip.
- Pins: sqlglot 30.14.0, click 8.4.2; dev pytest 9.1.1, ruff 0.15.4, black 26.5.1. Unchanged in
  Phase 2; no dependency was added.

## In progress

- Nothing. Phase 3 begins at `feat(extract): add laravel migration extractor` once Phase 2 is
  approved.

## Open questions for the owner

- `docs/architecture.md` calls `now()` a volatile default that still rewrites on PostgreSQL 11+.
  Postgres itself classifies `now()` as STABLE, so a real server treats
  `ADD COLUMN ... DEFAULT now()` as metadata-only from 11. The implementation follows the
  architecture document, since it is the source of truth, but this looks like a doc bug worth
  correcting: as written, migrate-guard reports a safe statement. `random()` and
  `gen_random_uuid()` are genuinely VOLATILE and the rule is correct for them.
- MG001's safe-widening list (varchar to longer varchar or text, numeric precision, varbit) can
  never be reached from a raw SQL file, because a single migration never states the old type. It
  is covered by unit tests over hand-built operations only. If it should stay unreachable, the
  simpler alternative is to drop the list and say plainly that every type change is reported.

## Decisions log

- 2026-07-27 - One intermediate operation IR for all three input formats. The extractors
  (sqlglot for SQL, regex for Laravel, ast for Django) normalize into a single `Operation`
  list, so each rule is written once and behaves identically across formats. The alternative
  (per-format rules) triples the rule surface and guarantees drift.
- 2026-07-27 - New-table exemption implemented in the engine, not per rule. Any operation on a
  table created in the same file is exempt from every rule, because a brand-new table has no
  rows or traffic. Centralizing it kills the largest false-positive class in one place and
  keeps rule modules focused on their own semantics.
- 2026-07-27 - MG004 (drops) cannot be ignored via config, only allowed per site with a
  mandatory reason. A global ignore of destructive operations silently rots; forcing the
  justification next to the DROP keeps the audit trail in the diff where the reviewer is
  looking.
- 2026-07-27 - Malformed suppression is exit 2, never a best-effort skip. An allow comment
  with a missing reason or unknown code aborts the run: a suppression mechanism that silently
  half-works is worse than none, because it teaches users their waivers are applied when they
  may not be.
- 2026-07-27 - Django `AlterField` is flagged conservatively as MG001 even though single-file
  introspection cannot see the previous field state (some AlterFields are metadata-only).
  Chosen over silence because a missed table rewrite costs an outage while a false positive
  costs one allow comment; the trade-off is stated in the finding message and documented in
  `docs/architecture.md`.
- 2026-07-28 - Statements are split with sqlglot's tokenizer, not a `;` string split. The tokens
  carry the source line, so every finding gets the true first line of its statement in a
  multi-statement file, and semicolons inside strings or comments cannot split a statement by
  accident.
- 2026-07-28 - Only a real sqlglot ParseError or TokenError becomes MG000. sqlglot silently
  downgrades syntax it does not model to a generic `Command` node (`SET lock_timeout`, `VACUUM`,
  unmodelled ALTER forms), and reporting those as unanalyzable would bury the real diagnostics
  in noise on valid SQL. Phase 2 maps the ALTER forms properly; a `Command` produces no
  operation and therefore no finding today.
- 2026-07-28 - `extract(path, text, dialect)` takes one argument more than the
  `extract(path, text)` signature sketched in `docs/architecture.md`. sqlglot cannot parse
  without a dialect (MySQL backticks against Postgres quoting), and the alternative, reading
  the config inside the extractor, would break the layering rule that extractors are pure.
  Flagged here rather than editing the architecture doc.
- 2026-07-28 - `MigrateGuardError` lives in `config.py` and is imported by discovery and the CLI.
  The layout in `docs/architecture.md` has no `errors.py` and the engineering rules forbid new
  utility modules without approval, so the exception sits with the first layer that raises it.
- 2026-07-28 - The config loader validates the whole documented schema now, including `ignore`
  and the `[[allow]]` entries, but Phase 1 does not apply either to findings; that is Phase 4's
  `feat(allow)` work. Validating in one place keeps the rejection paths (unknown key, bad enum,
  MG004 in `ignore`, allow without a reason) from being written twice.
- 2026-07-28 - sqlglot's logger is set to ERROR in `cli.main`. It warns on every `Command`
  fallback, which is normal for statements this tool does not model, and stderr belongs to
  migrate-guard's own one-line errors.
- 2026-07-28 - Summary counts follow the example in `docs/design.md`: the total counts every
  finding including allowed ones, while the per-severity and gating counts exclude allowed
  findings. The `github` example in `docs/api-contracts.md` counts its total differently; the
  design document wins because it specifies the text format.
- 2026-07-28 - `--dialect` stays a `click.Choice`, so an invalid flag value produces Click's
  usage error (exit 2, empty stdout) rather than the `error:` line. Usage errors are the arg
  parser's business; every migrate-guard configuration and environment error still uses the
  single documented format.
- 2026-07-28 - Message and fix lines wrap at 80 columns without breaking words or hyphenated
  tokens; statement excerpts are never wrapped, only capped at 200 characters in the IR, so
  nothing in the report depends on terminal width.
- 2026-07-29 - The two Postgres ALTER forms sqlglot does not model, `VALIDATE CONSTRAINT` and
  `ADD CONSTRAINT ... UNIQUE USING INDEX`, are recovered from the generic `Command` node's raw
  tail with two anchored, bounded regexes. Both are safe forms that MG001(c) and MG007 must
  recognize; leaving them unmapped would make the documented safe sequences produce exactly the
  false positives this phase exists to remove. Every other `Command` still produces no operation,
  so nothing is guessed at.
- 2026-07-29 - A raw SQL file never states a column's previous type, so `alter_column_type` always
  carries `old_type = None` and MG001(a) fires on every `ALTER COLUMN ... TYPE`. That is the
  documented conservative stance ("unknown old type is treated as a rewrite"); the safe-widening
  list is therefore exercised only by hand-built operations in `tests/test_rules_mg001.py`. Logged
  as an open question above rather than silently dropped.
- 2026-07-29 - Volatility of an `ADD COLUMN` default is decided by inversion: the default counts as
  constant only when its whole expression tree is made of literals, booleans, nulls, negation,
  parentheses, casts, arrays, and tuples. Anything containing a function call or a subquery is
  volatile. Listing volatile functions instead would silently pass every function the list forgot,
  and the failure direction there is a missed rewrite, not an extra allow comment.
- 2026-07-29 - A MySQL `CHANGE` that renames a column produces two operations, `rename_column` and
  `alter_column_type`, so it reports both MG005 and MG001. The statement really is both a rename
  and a full table copy, and suppressing either would hide half the risk. `CHANGE` with the same
  name on both sides produces only the type change.
- 2026-07-29 - MG009 reports at the first `dml` operation in file order and stays silent for the
  rest of the file, because the problem is the file's shape rather than any one statement. When
  that first data statement targets a table created in the same file the engine-wide new-table
  exemption skips it and the file goes unreported. That is deliberate: the exemption is documented
  as applying to every rule, and seeding a table created in the same migration is the safe case.
- 2026-07-29 - `add_check_not_valid` carries a `constraint` details key that the operation table in
  `docs/architecture.md` does not list. MG001(c) needs it to match a `CHECK (col IS NOT NULL)` to
  the `VALIDATE CONSTRAINT` that validates it by name; matching on "any validation of this table"
  would suppress the finding when the file validates some unrelated constraint. The key is
  additive and no documented field was renamed.
- 2026-07-29 - `rules/__init__.py` gained a small frozen `RuleInfo` dataclass and `catalog()`, and
  the unused Phase 1 `get_rule()` became `find()` over that catalog. MG000 is a diagnostic
  constructor rather than a `Rule`, so the `rules` and `explain` commands need one view that
  includes it; without it both commands would have to special-case MG000 separately.
- 2026-07-29 - `--postgres-version` was added to `check` inside the `feat(cli)` commit.
  `docs/api-contracts.md` documents the flag but no phase assigns it a commit, and MG001 and MG003
  semantics are unreachable from the command line without it, so the phase goal could not be
  demonstrated end to end. Folded into the one CLI commit of the phase rather than inventing an
  extra one.
- 2026-07-29 - Fixtures were restructured into `tests/fixtures/sql/{postgres,mysql}/{safe,unsafe}`,
  the layout `docs/testing.md` asks for, and the golden file was regenerated over the larger
  Postgres unsafe corpus. Deliberate regeneration reviewed in the diff, per the golden-file rule.
- 2026-07-29 - `fix(rules): correct mg009 message wording` is an eleventh commit beyond the ten
  listed for the phase. The message read "mixes schema changes with a UPDATE"; the defect surfaced
  after the rule was already pushed, and pushed history is never rewritten, so it is a new
  corrective commit rather than an amend.
- 2026-07-29 - `extractors/sql.py` is now around 400 lines, past the roughly 150-line guidance. It
  maps seventeen operation kinds across two dialects and is the single place where SQL syntax
  knowledge is allowed to live; splitting it by statement type would add modules without reducing
  the total or making any rule simpler. Flagged rather than split.
- 2026-07-29 - An `ALTER TABLE` that sqlglot keeps as a generic `Command` now produces MG000
  instead of nothing. The Phase 1 decision above (a `Command` produces no operation and therefore
  no finding) turned out to swallow every multi-action ALTER, the standard MySQL idiom and legal
  Postgres: `ALTER TABLE users ADD COLUMN a int, DROP COLUMN legacy_flag;` reported "no problems
  found" and exit 0, hiding MG004, the one code `ignore` is forbidden to silence. Only ALTER TABLE
  tails are reported; `ALTER TYPE`, `ALTER SEQUENCE`, `SET`, and `VACUUM` stay silent, so the
  noise argument from Phase 1 still holds where it applied. The cost is MG000 on a handful of
  table-level forms nobody models (`ENGINE=InnoDB`, `REPLICA IDENTITY FULL`,
  `ENABLE ROW LEVEL SECURITY`), which is the honest reading: migrate-guard did not check them.
- 2026-07-29 - Extraction catches `SqlglotError` and `RecursionError` per statement, not just
  `ParseError` and `TokenError`. A deeply nested expression raises `RecursionError` out of
  `sqlglot.parse_one`, which escaped the extractor, hit the CLI boundary, and aborted the entire
  run with exit 2 and an "internal error" line, taking every other file with it. The architecture
  requires extraction never to raise to the top, and a scanned file is hostile input. The
  statement mapping sits inside the same try for the same reason; genuine coding bugs
  (`AttributeError`, `KeyError`) are deliberately not caught, so they still surface loudly.
- 2026-07-29 - MG009 no longer counts a data statement whose table is created in the same file.
  The earlier entry called the interaction deliberate, but it went further than intended: the rule
  reports once, at the first `dml` operation, and when that statement was an exempt seed the
  engine skipped it while the rule still counted it, so a later backfill on a live table went
  unreported and the mixed file passed. A file whose only data statement is that seed is still
  silent, which is the case the original entry meant to protect.
