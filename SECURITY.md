# Security policy

## Supported versions

Only the latest release on `main` receives security fixes.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability reporting
(Security tab, "Report a vulnerability") or email thealirazadev@gmail.com with the
steps to reproduce. You should get a reply within 72 hours.

## How migrate-guard handles sensitive data

- No extractor imports, evaluates or executes the migration files it scans (`src/migrate_guard/extractors/__init__.py`).
- SQL is parsed with sqlglot, and Django migrations are read with Python's `ast` module (`src/migrate_guard/extractors/sql.py`, `src/migrate_guard/extractors/django.py`).
- Unknown keys or tables in `.migrateguard.toml` are reported as errors rather than ignored (`src/migrate_guard/config.py`).
