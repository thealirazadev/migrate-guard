"""MG002 - CREATE INDEX without CONCURRENTLY (Postgres).

A plain CREATE INDEX takes a SHARE lock on the table, which blocks every write
for as long as the build runs. CREATE INDEX CONCURRENTLY takes SHARE UPDATE
EXCLUSIVE instead and lets writes through, at the cost of a second table pass
and the requirement that it runs outside a transaction block.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from ..config import Config
from ..ir import Finding, Operation, OpKind

CONCURRENTLY_INSERT = re.compile(r"^(create\s+(?:unique\s+)?index)\b", re.IGNORECASE)


class MG002:
    code = "MG002"
    severity = "error"
    dialects = ("postgres",)
    summary = "CREATE INDEX without CONCURRENTLY"
    explanation = """MG002 fires on a CREATE INDEX statement that does not use CONCURRENTLY.

Postgres builds a plain index under a SHARE lock on the table. SHARE conflicts with
ROW EXCLUSIVE, the lock every INSERT, UPDATE, and DELETE takes, so every write to the
table waits until the index finishes building. On a large table that is minutes of
downtime for anything that writes.

Unsafe:

    CREATE INDEX users_email_idx ON users (email);

Safe:

    CREATE INDEX CONCURRENTLY users_email_idx ON users (email);

CREATE INDEX CONCURRENTLY takes SHARE UPDATE EXCLUSIVE, which does not conflict with
writes. It cannot run inside a transaction block, so the migration has to be run
outside one: in Django set atomic = False on the Migration and use
AddIndexConcurrently, in Laravel issue it with DB::statement from a migration whose
$withinTransaction is false. A concurrent build can leave an invalid index if it
fails, so check pg_index.indisvalid and drop and rebuild when it does.

Suppress one occurrence with an inline allow carrying a reason:

    -- migrate-guard: allow MG002 reason="table is empty at this point, OPS-1123"
"""

    def check(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None:
        if op.kind is not OpKind.create_index or op.details.get("concurrent"):
            return None
        target = op.table or "the table"
        return Finding(
            code=self.code,
            severity=self.severity,
            span=op.span,
            table=op.table,
            message=(
                f"CREATE INDEX without CONCURRENTLY blocks all writes to {target} "
                "for the duration of the build."
            ),
            safe_alternative=_safe_alternative(op.raw),
            statement=op.raw,
        )


def _safe_alternative(raw: str) -> str:
    rewritten, count = CONCURRENTLY_INSERT.subn(r"\1 CONCURRENTLY", raw, count=1)
    if count:
        return f"{rewritten.rstrip(';')}; run it outside a transaction."
    return (
        "Build the index with CREATE INDEX CONCURRENTLY instead, and run it outside a "
        "transaction."
    )


RULE = MG002()
