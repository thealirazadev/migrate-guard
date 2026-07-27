# Phases - migrate-guard

**Rule: phase N+1 does not start until the owner approves phase N.** Phases are ordered
smallest-useful-shippable first; each ends green (ruff, black, pytest clean). One commit per
feature/task, Conventional Commits, in the listed order.

The senior differentiators are placed early: the never-execute guarantee and MG000 diagnostics
land in Phase 1 with the SQL pipeline; the false-positive discipline (version gates, new-table
exemption, safe-form suppression) is the whole of Phase 2 and may not slip.

---

## Phase 1 - Foundation and the SQL pipeline

**Goal**: `migrate-guard check db/migrations` over raw SQL files reports MG002 and MG004
findings as text with correct exit codes. The smallest slice that already gates a CI job.

### Tasks

- Package scaffold: src layout, `pyproject.toml` with exact pins (sqlglot, click; dev: pytest,
  ruff, black), committed `uv.lock`, `migrate-guard` console script entry point.
- `ir.py`: `SourceSpan`, `Operation`, `OpKind`, `Allow`, `Finding` frozen dataclasses exactly
  as specified in `docs/architecture.md`.
- Config loader: `.migrateguard.toml` with strict unknown-key rejection, enum validation,
  `--dialect`/`--config` CLI overrides, `.migrateguard.toml.example` kept current.
- Discovery: recursive path resolution, extension-based format classification (only `.sql`
  wired up this phase), unreadable-file exit-2 path.
- SQL extractor on sqlglot: per-statement parse, operation mapping for the kinds MG002/MG004
  need plus `create_table`, MG000 diagnostic on unparseable statements, line numbers correct
  for multi-statement files.
- Engine with the rule registry and the new-table exemption; MG002 and MG004 rule modules as
  the pattern for all later rules.
- Text reporter (per `docs/design.md`) and exit-code mapping; `check` command wiring it all.
- CI workflow: ruff, black --check, pytest on push and PR.

### Expected commits

1. `build: scaffold package with pyproject, pinned deps, and tool config`
2. `chore: add gitignore and config example`
3. `feat(ir): add operation, allow, and finding dataclasses`
4. `feat(config): add toml config loader with strict key validation`
5. `feat(discovery): add migration file discovery over configured paths`
6. `feat(extract): add sql extractor built on sqlglot with mg000 diagnostics`
7. `feat(engine): add rule registry and new-table exemption`
8. `feat(rules): add mg002 create index without concurrently`
9. `feat(rules): add mg004 drop column and drop table`
10. `feat(report): add text reporter with verdict line`
11. `feat(cli): add check command with exit code mapping`
12. `build(ci): add lint and test workflow`
13. `test(phase1): cover config, extractor, rules, reporter, and cli`

### Verification checklist

- [ ] `uv sync` then `uv run migrate-guard check tests/fixtures/sql/unsafe` prints MG002 and
      MG004 findings with file, line, statement excerpt, and safe alternative; exit 1.
- [ ] The safe fixtures (CONCURRENTLY; drops inside a file that creates the table) exit 0 with
      "no problems found".
- [ ] A file with one garbage statement between two valid ones yields MG000 at the right line
      plus findings for the valid statements; never a traceback.
- [ ] Unknown config key, bad dialect, missing paths, unreadable file: each exits 2 with a
      one-line `error:` on stderr and nothing on stdout.
- [ ] Findings are sorted by (file, line, code) and two consecutive runs are byte-identical.
- [ ] `uv run ruff check .`, `uv run black --check .`, `uv run pytest` all clean; CI green.

---

## Phase 2 - The full rule catalog with false-positive discipline

**Goal**: all nine rules fire on their unsafe forms and stay silent on their safe forms, per
dialect and `postgres_version`. This phase is the product's credibility; it does not ship until
the safe-form matrix is fully green.

### Tasks

- Extend the SQL extractor to every `OpKind` in `docs/architecture.md` (alter type, not null,
  check/validate, renames, FKs, unique constraints, enum forms, DML).
- MG001 with the safe-widening list, the pre/post-11 default semantics, volatile-default
  detection, and the MG001(c) same-file CHECK/VALIDATE suppression.
- MG003 with the MG001(b) escalation seam (default present + pre-11 goes to MG001, not MG003).
- MG005, MG006, MG007 including the `USING INDEX` safe form.
- MG008 heuristics (MySQL enum redefinition, Postgres drop_type) with honest messages.
- MG009 file-level DDL/DML detection, MySQL-gated.
- `rules` and `explain` commands rendering each rule's summary and long explanation.

### Expected commits

1. `feat(extract): map full sql operation set`
2. `feat(rules): add mg001 table rewrite and lock detection`
3. `feat(rules): add mg003 not null column without default`
4. `feat(rules): add mg005 rename column and table`
5. `feat(rules): add mg006 foreign key without not valid`
6. `feat(rules): add mg007 unique constraint without concurrent index`
7. `feat(rules): add mg008 enum removal heuristics`
8. `feat(rules): add mg009 mixed ddl and dml on mysql`
9. `feat(cli): add rules and explain commands`
10. `test(phase2): cover unsafe and safe forms per dialect and version`

### Verification checklist

- [ ] Per-rule test matrix: every documented unsafe form produces exactly its code; every
      documented safe form produces nothing. The matrix covers both dialects and
      `postgres_version` 10, 11, 12, and 16.
- [ ] `ADD COLUMN ... NOT NULL DEFAULT 0` with version 16: no finding. Same with version 10:
      MG001 only. Same without DEFAULT on either: MG003 only.
- [ ] The CHECK NOT VALID + VALIDATE + SET NOT NULL sequence in one file on version 12+: no
      MG001(c); the bare SET NOT NULL still fires.
- [ ] Postgres-only rules never fire under `dialect = "mysql"` and vice versa; the new-table
      exemption holds for every rule.
- [ ] `migrate-guard rules` lists all ten codes; `explain MG001` prints the long form;
      `explain MG999` exits 2.
- [ ] ruff, black, pytest clean; CI green.

---

## Phase 3 - Laravel and Django extractors

**Goal**: the same dangerous change written as Laravel PHP or a Django migration yields the
same findings as its raw-SQL equivalent, still without executing anything.

### Tasks

- Laravel extractor: `Schema::create/table/drop/dropIfExists/rename`, column methods with
  `->change()`, `dropColumn`, `renameColumn`, index/unique/foreign builders, `DB::statement`
  and `DB::unprepared` literals routed through the SQL extractor; comment/string stripping
  before matching; MG000 for recognized-but-unextractable calls.
- Django extractor: `ast.parse`, locate `Migration.operations`, map `CreateModel`,
  `DeleteModel`, `AddField`, `AlterField`, `RemoveField`, `RenameField`, `RenameModel`,
  `AddIndex`, `AddIndexConcurrently` (with the `atomic = False` requirement), `AddConstraint`,
  `AlterUniqueTogether`, `RunSQL` literals; `RunPython` ignored by design.
- Discovery wiring for `.php` and `.py`, including non-migration `.py` rejection (MG000).
- Booby-trapped fixtures proving the never-execute guarantee for both formats.
- Parity fixtures: one dangerous change expressed three ways, asserted to produce identical
  codes.

### Expected commits

1. `feat(extract): add laravel migration extractor`
2. `feat(extract): add django migration extractor`
3. `feat(discovery): wire php and python formats`
4. `test(phase3): cover extraction, parity, and never-execute guarantees`
5. `docs: add framework support notes to readme`

### Verification checklist

- [ ] The parity fixture trio (SQL, Laravel, Django versions of the same migration) produces
      identical rule codes at plausible lines.
- [ ] Booby-trap fixtures (Django top-level side effect, PHP backticks/eval) are scanned with
      zero side effects, asserted by test.
- [ ] `AddIndexConcurrently` without `atomic = False` fires MG002 with the atomic message; with
      it, no finding.
- [ ] `DB::statement` with a variable argument yields MG000, not a guess; a Laravel file whose
      schema calls sit inside comments yields nothing.
- [ ] A 1 MB single-line PHP file completes in under a second (regex boundedness).
- [ ] ruff, black, pytest clean; CI green.

---

## Phase 4 - Suppression, diff-base mode, and machine formats

**Goal**: teams can adopt migrate-guard in a repo with history, waive findings with recorded
justifications, and consume output as JSON or GitHub annotations.

### Tasks

- Inline allow comments in all three formats: grammar, scope, mandatory reason, exit-2 on
  malformed allows, stale-allow stderr warning.
- Config `[[allow]]` entries and `ignore` list, with the MG004/MG000 ignore rejection.
- `--diff-base`: merge-base resolution, changed-file intersection, ref validation, git failure
  handling, "no migration files to check" empty result.
- JSON reporter (stable schema from `docs/api-contracts.md`) and GitHub annotations reporter.
- `--fail-on` flag completing the gating contract.

### Expected commits

1. `feat(allow): add inline allow comments with required reason`
2. `feat(allow): add config allowlist and ignore handling`
3. `feat(diff): add diff base mode over git changed files`
4. `feat(report): add json reporter`
5. `feat(report): add github annotations reporter`
6. `test(phase4): cover allows, diff mode, and both machine formats`

### Verification checklist

- [ ] An inline allow with reason suppresses exactly one finding, which still appears marked
      allowed with its reason in all three formats; exit 0 when nothing else gates.
- [ ] Allow without reason, unknown code in an allow, `ignore = ["MG004"]`: each exits 2
      naming the offending location.
- [ ] In a scratch git repo: `--diff-base main` lints only files added/changed on the branch;
      unchanged unsafe history produces nothing; a renamed-and-edited file is linted; unknown
      ref exits 2 with git's message.
- [ ] JSON output validates against the documented schema and is byte-identical across runs;
      `--format github` emits correct workflow-command lines (title, file, line).
- [ ] `--fail-on warning` makes an MG008-only run exit 1; default leaves it exit 0.
- [ ] ruff, black, pytest clean; CI green.

---

## Phase 5 - GitHub Action and distribution

**Goal**: a repository can adopt migrate-guard with five lines of workflow YAML, and the
package is releasable to PyPI.

### Tasks

- `action.yml` composite action: inputs (`paths`, `config`, `diff-base`, `fail-on`, `format`,
  `version`), PR-aware diff-base default (`origin/<base_ref>`), pinned install, run step.
- Self-test workflow exercising the action against the repo's own fixtures (expected-failure
  job asserting exit 1 and annotation output).
- Release workflow: build sdist/wheel on tag, publish to PyPI (trusted publishing), version
  single-sourced from `migrate_guard/__init__.py`.
- README finalized: install, quickstart, rule table, config reference, action usage, adoption
  guide (diff-base first, then full); status line updated from planning to released.

### Expected commits

1. `feat(action): add composite github action`
2. `build(ci): add action self-test workflow`
3. `build: add release workflow publishing to pypi`
4. `docs: finalize readme with adoption guide`
5. `docs: log phase five completion in memory`

### Verification checklist

- [ ] The self-test workflow's failing job shows inline annotations on the fixture file and
      the job fails; the passing job (safe fixtures) succeeds.
- [ ] `uv build` produces a wheel; `pip install dist/*.whl` in a clean venv gives a working
      `migrate-guard --version`.
- [ ] Action inputs override config as documented; omitting `diff-base` on a PR defaults to
      the base branch; a push event without a base runs the full tree.
- [ ] README quickstart commands run verbatim on a clean checkout.
- [ ] ruff, black, pytest clean; CI green including the action self-test.

---

## Backlog

- Alembic and Rails extractors - the IR was designed for them, but each needs its own
  safe-extraction story and fixture corpus; out of scope for this build.
- `--explain` inline in findings output (full explanation per finding) - wait for user demand;
  the `explain` command covers it.
- SARIF output for GitHub code scanning - only if a real consumer appears; the annotations
  format covers PR review today.
- Configurable per-rule severity overrides - deliberately excluded until real-world usage shows
  the defaults are wrong somewhere; severity stability is part of the CI contract.
