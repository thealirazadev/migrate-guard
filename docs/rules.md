# Engineering Rules - migrate-guard

These rules are binding for every change in this repository and extend the workspace-level
engineering rules.

## Conventions

- **Layered pipeline, no shortcuts**: CLI orchestrates; extractors produce `Operation` lists;
  rules consume operations; reporters consume findings. A rule never reads a file, an extractor
  never creates a `Finding` other than MG000, a reporter never inspects an `Operation`. All
  cross-layer data goes through the frozen dataclasses in `ir.py`.
- **Preferred libraries**: sqlglot for all SQL parsing, Click for the CLI, `tomllib` for config,
  `ast` for Django files, `re` for Laravel files. Do not add a PHP parser, a TOML writer, a
  colorama-style dependency (ANSI codes are written directly), or any YAML/JSON schema library.
- **What to avoid**: no `exec`/`eval`/`importlib` on scanned content under any circumstance; no
  network access anywhere; no writes to disk at runtime; no global mutable state (the rule
  registry is populated at import time and frozen); no `print()` outside `reporters/` and the
  CLI error path; no environment variable reads outside the two documented in
  `docs/architecture.md`.
- **Rule module pattern**: each `rules/mgNNN.py` exposes one `Rule` with `code`, `severity`,
  `dialects`, `check(op, file_ops, index, config) -> Finding | None`, a one-line `summary`, and
  a multi-paragraph `explanation` used by `explain`. Once MG002 is approved, every other rule
  copies its exact structure. Detection logic stays inside the rule module; shared helpers go in
  `rules/base.py` only when three rules need them.
- **Naming**: PEP 8 throughout; modules named for their role (`engine.py`, `discovery.py`);
  rule codes are the literal strings `MG000`-`MG009` and appear nowhere as integers; `OpKind`
  values are the exact snake_case strings in `docs/architecture.md` - never introduce synonyms.
- **Commit format**: Conventional Commits, short imperative subject, lower case after the
  prefix, e.g. `feat(rules): add mg002 create index without concurrently`. Scopes: `ir`,
  `config`, `discovery`, `extract`, `engine`, `rules`, `allow`, `diff`, `report`, `cli`,
  `action`, `ci`.
- **ONE COMMIT PER FEATURE**: exactly the commits listed per phase in `docs/phases.md`, in
  order. Never batch features, never fragment one small feature.
- **Pin exact dependency versions**: `==` pins in `pyproject.toml`, `uv.lock` committed. Any
  dependency change is its own `build:` commit and needs owner approval first.
- **Determinism is a feature**: any code path that could reorder findings (dict iteration,
  glob results, set operations) must sort explicitly. Golden-file tests enforce byte-identical
  output; do not weaken them to "contains".

## Error handling & logging

- **Every fallible call handles failure**: file reads, `tomllib.load`, `sqlglot.parse`,
  `ast.parse`, and the git subprocess each have an explicit failure path mapped in the
  failure-modes table in `docs/architecture.md`. No bare calls that assume success.
- **Content problems are findings, environment problems are exits**: anything wrong inside a
  scanned file becomes MG000 and the run continues; anything wrong with config, paths,
  permissions, or git aborts with exit 2 and a one-line message. Never blur this line - it is
  what makes the tool safe to run in CI.
- **No tracebacks to users**: expected failures print `error: <one sentence>` to stderr and
  exit 2. Unexpected exceptions are caught at the CLI boundary, printed as a one-line internal
  error, and re-raised only when `MIGRATE_GUARD_DEBUG=1`.
- **stdout is the report, stderr is everything else**: findings and reports go to stdout in the
  selected format; errors, stale-allow warnings, and progress go to stderr. CI consumers parse
  stdout; never pollute it.
- **One error format**: `error: <message>` on stderr, exit 2, for every configuration and
  environment error. No variants, no multi-line errors, no partial reports after an error.

## Security

- **Scanned files are hostile input**: migration files come from arbitrary repositories. They
  are parsed, never executed, imported, or shelled. The booby-trap fixtures in `tests/` are the
  regression net for this guarantee; extending an extractor requires extending them.
- **Regex discipline (Laravel extractor)**: every regex is anchored or bounded, uses no nested
  unbounded quantifiers (ReDoS), and is tested against pathological inputs (a 1 MB single-line
  file must complete in linear time). Comment and string contexts are stripped before matching
  so SQL inside a PHP comment cannot produce findings.
- **git subprocess hygiene**: fixed argument vector, `shell=False`, no user input interpolated
  into the command beyond the ref name, which is validated against `^[\w./@^~-]+$` first.
- **No secrets**: the tool needs none, reads none, and must never log file contents beyond the
  200-char statement excerpt already defined in the IR.
- **Path traversal**: discovery never follows symlinks out of the scan roots; reported paths
  are always the user-supplied form, never resolved absolute paths (CI logs should not leak
  runner filesystem layout).

## Simplicity / YAGNI-KISS

- Build only what the current phase requires. No plugin system, no custom-rule API, no config
  inheritance, no caching layer, no parallelism - a lint run is milliseconds of CPU.
- No abstraction until three real use cases exist. The `Rule` protocol is justified by ten
  concrete rules; the extractor interface by three formats; nothing else warrants one.
- No new wrapper classes, managers, or utils modules without owner approval first.
- If a solution exceeds roughly 150 lines, pause and justify it before continuing.

## Code style

- Comments are sparse and explain why, not what. The lock-semantics reasoning inside each rule
  deserves a concise docstring citing the behavior it encodes; getters do not.
- No emoji anywhere in code, comments, commits, or docs. No AI or authorship attribution
  anywhere - no generated-by notes, no co-author trailers.
- ruff and black own formatting and linting; do not hand-format against them.

## Boundaries - never do without asking the owner first

- **No wholesale delete/rewrite** of working files; targeted edits, destructive changes flagged.
- **Do not change `docs/PRD.md` or `docs/architecture.md`** without flagging the change and
  getting sign-off - they are the source of truth.
- **No new dependency without approval**; propose what, why, version, and size, then wait.
- **Never change a rule's default severity, dialect gate, or detection scope** outside an
  approved phase - CI gates in user repositories depend on them.
- **Stop after two failed fix attempts** on the same problem and report instead of thrashing.
- **Scope discipline**: any mid-phase request not in `docs/PRD.md` is classified with the owner
  as current phase, new phase, or Backlog in `docs/phases.md`. Never silently absorb scope.
