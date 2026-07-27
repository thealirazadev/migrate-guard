# Design - migrate-guard

migrate-guard has no graphical UI; its surfaces are the terminal output of the CLI, the JSON
document, and GitHub PR annotations. Visual-design sections are replaced by the CLI-UX
equivalents below. The design goal is a report a reviewer can act on in one read: what is
dangerous, where, and exactly what to write instead.

## Text format (`--format text`, the default)

```
db/migrations/0042_add_email_index.sql
  7  MG002  error    CREATE INDEX without CONCURRENTLY blocks all writes to
                     users for the duration of the build.
                     statement: CREATE INDEX users_email_idx ON users (email)
                     fix: CREATE INDEX CONCURRENTLY users_email_idx ON users (email);
                          run it outside a transaction.

db/migrations/0043_cleanup.sql
  3  MG004  error    DROP TABLE removes audit_legacy and its data permanently.
                     allowed: "retired 2026-06, approved OPS-1123"

checked 12 files, 41 statements
2 findings: 1 error (1 gating), 0 warnings, 1 allowed
verdict: FAIL (fail_on = error)
```

- Findings grouped by file, ordered by line; files ordered by path. Each finding: line, code,
  severity, one-sentence message, the statement excerpt, and the `fix:` line with concrete
  replacement statements - never "consider a safer approach".
- Allowed findings render with `allowed:` and the justification instead of `fix:`, so waived
  danger stays visible in every run.
- The summary block is always last: files/statements counted, findings by severity with the
  gating count, then the verdict line. `verdict:` always states the effective `fail_on`, on
  PASS as much as FAIL, so the gate is never a mystery.
- A clean run prints the counts and `verdict: PASS`; an empty file set prints
  `no migration files to check` and `verdict: PASS` (normal in diff-base mode).
- Continuation lines are indented to align under the message column; no table-drawing
  characters, no progress spinners; output is identical piped to a file.

## Color

- ANSI color only when stdout is a TTY and `NO_COLOR` is unset: red for `error` and `FAIL`,
  yellow for `warning`, cyan for rule codes, dim for statement excerpts, green for `PASS`.
- Color is never the only signal: severity words and the verdict text carry the meaning; piped
  output is byte-identical minus escape codes.

## Errors and exit codes

- Errors go to stderr as `error: <one clear sentence>`, with one remedy line where useful
  (`add dialect = "postgres" to .migrateguard.toml or pass --dialect`). Never a traceback for
  expected failures; `MIGRATE_GUARD_DEBUG=1` re-raises for bug reports.
- Exit codes: `0` pass (including allowed-only), `1` gating findings, `2` configuration or
  environment error. Stdout stays empty on exit 2 - a partial report is worse than none.

## `rules` and `explain` commands

- `migrate-guard rules`: one aligned row per rule - code, default severity, dialects, one-line
  summary - ordered by code. Fits on one screen; no pager.
- `migrate-guard explain MG001`: the rule's summary, why the operation is dangerous (named
  locks and rewrite behavior, version specifics), an unsafe example, the safe alternative as
  runnable statements, and the suppression note (inline allow grammar). Plain paragraphs
  wrapped at 100 columns, readable when piped.

## JSON format (`--format json`)

One document on stdout, schema fixed in `docs/api-contracts.md`: tool version, dialect, counts,
and the findings array sorted (file, line, code); key order fixed; no color, no TTY behavior.
Designed for diffing between CI runs, so ordering and key stability are part of the contract.

## GitHub annotations format (`--format github`)

One workflow-command line per finding
(`::error file=...,line=...,title=MG002::message Safe alternative: ...`), warnings as
`::warning`. Allowed findings become `::notice` lines carrying the justification, so waivers
surface in PR review too. The summary and verdict go to stdout as plain lines after the
commands (visible in the job log, ignored by the annotation parser).

## Accessibility baseline

No color-only meaning and `NO_COLOR` respect (above); layout is linear and labeled for screen
readers (no ASCII art beyond indentation); messages are complete sentences naming the object
("blocks all writes to users"), not fragments; `--help` for every command states defaults and
accepted values. Wide statements are excerpted at 200 chars rather than wrapped mid-token, so
nothing depends on terminal width.
