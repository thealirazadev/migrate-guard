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

## Project status

- Phase 1 shipped and verified locally; Phase 2 (full rule catalog and false-positive discipline)
  not started, awaiting owner approval.
- Verified on 2026-07-28 with Python 3.12.3 and uv 0.11.28: `uv sync`, `uv run ruff check .`,
  `uv run black --check .`, and `uv run pytest` all clean (76 passed); the unsafe fixtures exit 1
  with MG002, MG004, and MG000 at the right lines, the safe fixtures exit 0 with
  "no problems found", every exit-2 path prints one `error:` line on stderr with empty stdout,
  and two consecutive runs are byte-identical.
- CI: green on the Phase 1 tip. The workflow's own commit (`build(ci)`) shows a red run, because
  at that commit the test suite did not exist yet and pytest exits 5 when it collects nothing;
  the next commit adds the suite and every run from there is green. Left as history rather than
  rewritten, since the phase ends green and the commit order is fixed by `docs/phases.md`.
- Pins: sqlglot 30.14.0, click 8.4.2; dev pytest 9.1.1, ruff 0.15.4, black 26.5.1.

## In progress

- Nothing. Phase 2 begins at `feat(extract): map full sql operation set` once Phase 1 is
  approved.

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
