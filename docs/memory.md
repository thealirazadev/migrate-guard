# Project Memory - migrate-guard

Running log of what is done, in progress, and decided. Update after every meaningful chunk of
work; log every non-obvious decision with its reason. Keep entries short and dated.

## Completed

- 2026-07-27 - Planning documentation created (README, PRD, architecture, rules, phases,
  design, testing, api-contracts, launch-checklist, memory). No code yet; docs under owner
  review. Implementation follows `docs/phases.md` starting with Phase 1 once approved.

## Project status

- Planning stage. All ten planning documents drafted; awaiting owner review before Phase 1.

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
