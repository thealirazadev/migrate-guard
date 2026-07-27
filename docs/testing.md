# Testing - migrate-guard

## Strategy

- **pytest** is the framework. Tests make zero network calls and never execute scanned
  content; the only subprocess any test spawns is `git`, inside a scratch repo built in
  `tmp_path` for diff-base tests.
- **Fixture corpus over inline strings.** `tests/fixtures/{sql,laravel,django}/` holds real
  migration files split into `unsafe/` and `safe/` per dialect. Every rule's unsafe and safe
  forms exist as fixtures; a rule change without a fixture change is suspect. Inline strings
  are acceptable only for config-loader and grammar edge cases.
- **Unit tests** for the pure logic: config validation (every rejection path), the allow
  grammar, operation mapping per extractor, each rule's `check` against hand-built operation
  lists (both dialects, `postgres_version` 10/11/12/16), the new-table exemption, same-file
  lookback, and finding sort order.
- **CLI tests** through Click's `CliRunner`: every exit code, stdout/stderr separation (stdout
  empty on exit 2), flag overrides beating config, `rules`/`explain` output, `--fail-on`
  gating.
- **Golden-file tests** for the three reporters: expected output committed under
  `tests/fixtures/golden/` and compared byte-for-byte (ANSI stripped via `NO_COLOR`). Golden
  files are regenerated only deliberately, reviewed in the diff.
- **Never-execute guarantee**: booby-trapped fixtures (a Django migration with a top-level
  file write, a PHP file with backtick and eval constructs) are scanned by a test that asserts
  the sentinel side effect did not occur. This test is the security contract; it never gets
  skipped or weakened.
- **Determinism test**: the full fixture tree linted twice must produce byte-identical output.

### What gets unit vs integration vs e2e coverage

- Unit: rules, config, allow grammar, IR mapping - fast, exhaustive, matrix-driven.
- Integration: extractor + engine + reporter over fixture files via `CliRunner`; the diff-base
  flow against a real scratch git repo (commit history built per test).
- End to end: the GitHub Action self-test workflow in CI (Phase 5) runs the packaged CLI
  against the repo's own fixtures and asserts the failing job fails with annotations; this is
  the only e2e layer and it runs in CI, not pytest.

Coverage target: every rule code, every documented safe form, every exit code, every failure
mode in `docs/architecture.md`, and every config rejection produced by at least one test.
Meaningful paths over percentages.

## Exact commands

```bash
uv sync                              # install from pyproject + committed uv.lock
uv run pytest                        # full suite, no network
uv run pytest tests/test_rules_mg001.py   # one file
uv run pytest -k "not_null"          # filter by name
uv run ruff check .                  # lint
uv run black --check .               # format check (black . to apply)
```

Build gate (must pass before any commit is declared done):

```bash
uv sync
uv run python -c "import migrate_guard"
uv run ruff check . && uv run black --check . && uv run pytest
```

Manual smoke run against the fixtures:

```bash
uv run migrate-guard check tests/fixtures/sql/unsafe --dialect postgres   # expect exit 1
uv run migrate-guard check tests/fixtures/sql/safe --dialect postgres     # expect exit 0
uv run migrate-guard rules
uv run migrate-guard explain MG001
```

## CI plan

One workflow, two jobs from Phase 1: `lint` (ruff + black --check) and `test` (pytest) on
Python 3.12, on push and pull request to `main`. Phase 5 adds the action self-test workflow
(expected-pass and expected-fail jobs against the fixture corpus) and the tag-triggered release
workflow (build + PyPI publish). No job needs secrets except the release publish step.

## Definition of "done" for a feature

1. `uv run ruff check .` and `uv run black --check .` - clean.
2. `uv run pytest` - full suite green, new tests included in the same commit series.
3. The phase's verification checklist items in `docs/phases.md` pass.

After creating or editing files, run the build gate and fix all errors before reporting done.
One commit per feature, in the order listed in `docs/phases.md`.
