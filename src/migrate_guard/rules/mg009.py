"""MG009 - DDL and DML in one migration file (MySQL).

MySQL commits implicitly before and after every DDL statement, so a migration
that mixes schema changes with data changes is not one transaction no matter
what the framework wraps around it. A failure halfway through leaves the
schema partly changed and the data partly written, and rerunning the file often
fails on the part that already succeeded.

The rule is file-level: it reports once, at the first data statement, rather
than once per statement, because the problem is the file's shape.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..config import Config
from ..ir import Finding, Operation, OpKind


class MG009:
    code = "MG009"
    severity = "warning"
    dialects = ("mysql",)
    summary = "DDL and DML mixed in one migration"
    explanation = """MG009 fires once on a MySQL migration file that contains both a schema
statement and a data statement.

MySQL performs an implicit commit before and after each DDL statement. A file like
this one is therefore three transactions, not one:

    ALTER TABLE users ADD COLUMN status varchar(20);
    UPDATE users SET status = 'active' WHERE status IS NULL;
    ALTER TABLE users MODIFY status varchar(20) NOT NULL;

If the UPDATE fails halfway, the column exists, some rows are set, and the migration
tool records the migration as failed. Rerunning it fails on the ADD COLUMN, so the
recovery is manual every time.

Safe: split the file. One migration performs the schema change, a second performs the
backfill in bounded batches with its own restart safety, a third applies any
constraint that depends on the backfill. Each is rerunnable on its own.

Postgres is not affected: its DDL is transactional, so a mixed migration rolls back
cleanly, and MG009 never fires under dialect = "postgres".

MG009 is a warning and does not gate a build unless fail_on = "warning". Suppress one
occurrence with a reason:

    -- migrate-guard: allow MG009 reason="seed data for a table created in this file"
"""

    def check(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None:
        if op.kind is not OpKind.dml:
            return None
        if any(earlier.kind is OpKind.dml for earlier in file_ops[:index]):
            return None
        if not any(other.kind is not OpKind.dml for other in file_ops):
            return None
        verb = str(op.details.get("verb") or "data").upper()
        return Finding(
            code=self.code,
            severity=self.severity,
            span=op.span,
            table=op.table,
            message=(
                f"This migration mixes schema changes with data changes ({verb}); MySQL "
                "commits implicitly around DDL, so the file is not atomic and a mid-file "
                "failure leaves partial state."
            ),
            safe_alternative=(
                "Split the file: one migration for the schema change, a second for the "
                "backfill in bounded batches, a third for any constraint that depends on "
                "it. Each one is then rerunnable on its own."
            ),
            statement=op.raw,
        )


RULE = MG009()
