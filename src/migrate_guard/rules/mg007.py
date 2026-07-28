"""MG007 - a UNIQUE constraint that builds its own index (Postgres).

ADD CONSTRAINT ... UNIQUE builds the backing index while holding ACCESS
EXCLUSIVE, so the table is unavailable for reads and writes until the build
finishes. Building the index concurrently first and attaching it with USING
INDEX moves all of that work outside the lock; only the attach is blocking, and
it is instant.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..config import Config
from ..ir import Finding, Operation, OpKind


class MG007:
    code = "MG007"
    severity = "error"
    dialects = ("postgres",)
    summary = "UNIQUE constraint without a concurrent index first"
    explanation = """MG007 fires on ALTER TABLE ... ADD CONSTRAINT ... UNIQUE that is not
attached to an index built beforehand.

A unique constraint is a unique index plus a catalog entry. Adding the constraint
directly builds that index under ACCESS EXCLUSIVE, which blocks every read and write
to the table for the whole build. On a large table this is the same outage as a
non-concurrent CREATE INDEX (MG002), with the same fix available.

Unsafe:

    ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email);

Safe, in two steps:

    -- 1. build the index without blocking writes; run it outside a transaction
    CREATE UNIQUE INDEX CONCURRENTLY users_email_key ON users (email);

    -- 2. attach it; this takes ACCESS EXCLUSIVE but returns immediately
    ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE USING INDEX users_email_key;

If step 1 fails it leaves an invalid index behind: check pg_index.indisvalid, drop
it, and rebuild before retrying. The USING INDEX form never produces a finding.

Suppress one occurrence with an inline allow carrying a reason:

    -- migrate-guard: allow MG007 reason="table is seeded empty in this release"
"""

    def check(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None:
        if op.kind is not OpKind.add_unique_constraint or op.details.get("using_index"):
            return None
        table = op.table or "the table"
        return Finding(
            code=self.code,
            severity=self.severity,
            span=op.span,
            table=op.table,
            message=(
                f"Adding a UNIQUE constraint to {table} builds its index under ACCESS "
                "EXCLUSIVE, which blocks reads and writes for the whole build."
            ),
            safe_alternative=(
                f"Run CREATE UNIQUE INDEX CONCURRENTLY <name> ON {table} (...); outside a "
                f"transaction first, then ALTER TABLE {table} ADD CONSTRAINT <name> UNIQUE "
                "USING INDEX <name>;"
            ),
            statement=op.raw,
        )


RULE = MG007()
