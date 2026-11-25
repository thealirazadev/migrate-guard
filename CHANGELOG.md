# Changelog

## Unreleased

### Added
- The `check` command exits with codes that map to the lint result.
- The `rules` and `explain` commands were added.
- The text reporter prints a verdict line.
- Rule MG009 flags mixed DDL and DML on MySQL.
- Rule MG008 flags enum value removal.
- Rule MG007 flags unique constraints added without a concurrent index.
- Rule MG006 flags foreign keys added without NOT VALID.
- Rule MG005 flags renames of columns and tables.
- Rule MG004 flags dropped columns and tables.
- Rule MG003 flags NOT NULL columns added without a default.
- Rule MG002 flags index creation without CONCURRENTLY.
- Rule MG001 detects table rewrites and lock-taking ALTER statements.
- The SQL extractor covers the full set of supported operations.
- Laravel and Django migration files are extracted and linted.
- Migration files are discovered from the configured paths, with PHP and Python formats wired in.

### Fixed
- Inline allow comments, config `[[allow]]` entries and the `ignore` list are applied; before,
  they were validated but every finding still gated. Malformed inline allows exit 2, and allows
  that match nothing print a warning.
- Rule codes in `ignore` and `[[allow]]` must exist, so a typo is rejected.
- The MG002 message explains why `atomic = False` is needed for concurrent index creation.
- Migrations package `__init__` files are skipped during discovery.
- Django operations get their default table and field names.
- Laravel linting covers only `up()`, so rollback drops in `down()` are not reported.
- Black was upgraded to patch security advisories.
- Seed data no longer silences MG009 for the rest of the file.
- Every parser failure is contained to the file that caused it.
- Unmapped ALTER TABLE statements are reported as MG000.
- The MG009 message wording was corrected.
