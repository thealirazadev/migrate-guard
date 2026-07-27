# Launch Checklist - migrate-guard

Work top to bottom before the first public release (PyPI + action tag). Nothing is checked
until verified against the built artifacts, not the working tree.

## Package and versioning

- [ ] `uv build` produces sdist and wheel; `pip install dist/*.whl` in a clean Python 3.12
      venv yields a working `migrate-guard --version`.
- [ ] Version single-sourced from `migrate_guard/__init__.py`; tag, package metadata, and
      `--version` output all agree.
- [ ] `uv.lock` committed and consistent with the exact pins in `pyproject.toml`.
- [ ] Package metadata complete: description, license, `Programming Language :: Python :: 3.12`,
      repository URL; README renders correctly on PyPI (check with a dry-run build).
- [ ] No unintended files in the wheel (fixtures, docs, tests excluded).

## Correctness gates

- [ ] Full test suite green in CI on a fresh clone; ruff and black clean.
- [ ] Golden-file outputs reviewed one final time for wording quality (these strings are the
      product).
- [ ] Determinism check: two full runs over the fixture corpus byte-identical.
- [ ] Never-execute test present and passing; booby-trap fixtures cover both PHP and Django.
- [ ] False-positive spot check against two real-world repos (one Laravel, one Django): every
      reported finding is genuinely dangerous or explicitly heuristic (MG008/MG000); no safe
      form flagged.

## GitHub Action

- [ ] Action self-test workflow green: expected-fail job fails with inline annotations at the
      right file and line; expected-pass job passes.
- [ ] Action pins its own migrate-guard version; `version` input override verified.
- [ ] PR event defaults to diff-base linting; push event runs the full tree; both verified in
      a scratch repository using the tagged action, not a local path.
- [ ] `v1` major tag created and points at the release commit.

## Documentation

- [ ] README quickstart runs verbatim on a clean checkout; rule table matches
      `migrate-guard rules` output exactly.
- [ ] `.migrateguard.toml.example` matches the config contract in `docs/api-contracts.md`.
- [ ] `explain` text for all ten codes proofread; safe alternatives are runnable statements.
- [ ] README status line updated from planning to released; adoption guide (diff-base first,
      then full runs) present.

## Release mechanics

- [ ] PyPI trusted publishing configured; release workflow runs on tag and publishes; no API
      token stored in the repo.
- [ ] Changelog entry for the release listing every rule code shipped.
- [ ] Install from PyPI (not the local wheel) smoke-tested: `pip install migrate-guard` then
      the manual smoke commands from `docs/testing.md`.
- [ ] Repository housekeeping: LICENSE present, issue templates, description and topics set.
