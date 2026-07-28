"""MG005 - renaming a column or a table.

The rename itself is a catalog update and takes microseconds; the danger is the
deploy window. Between the migration and the last old pod being replaced, the
previous application version is still selecting the old name, which no longer
exists. Expand-contract is the only safe shape.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..config import Config
from ..ir import Finding, Operation, OpKind

RENAME_KINDS = (OpKind.rename_column, OpKind.rename_table)


class MG005:
    code = "MG005"
    severity = "error"
    dialects = ("postgres", "mysql")
    summary = "column or table rename breaks the deploy window"
    explanation = """MG005 fires on RENAME COLUMN and on renaming a table.

The statement is cheap: both engines update the catalog and return. The outage comes
from the rolling deploy. While the migration runs, instances of the previous release
are still issuing queries against the old name, and every one of them fails until
the last old instance is gone. Rolling back is worse, because the new name is the
only one that exists by then.

Unsafe:

    ALTER TABLE users RENAME COLUMN email TO primary_email;
    ALTER TABLE users RENAME TO people;

Safe, expand-contract, one migration per step:

    -- 1. add the new name
    ALTER TABLE users ADD COLUMN primary_email text;

    -- 2. deploy code that writes both names and reads the old one
    -- 3. backfill in batches
    UPDATE users SET primary_email = email WHERE primary_email IS NULL AND id < 10000;

    -- 4. deploy code that reads the new name
    -- 5. drop the old column, under an MG004 allow
    ALTER TABLE users DROP COLUMN email;

For a table, the same shape with a view: create the new table, dual-write, backfill,
switch reads, then drop the old table. MySQL can also keep the old name available
with a view over the new table during the cutover.

Suppress one occurrence with an inline allow carrying a reason:

    -- migrate-guard: allow MG005 reason="rename ships in a maintenance window, OPS-1201"
"""

    def check(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None:
        if op.kind not in RENAME_KINDS:
            return None
        table = op.table or "the table"
        new_name = op.details.get("new_name") or "the new name"
        if op.kind is OpKind.rename_table:
            message = (
                f"Renaming {table} to {new_name} removes the old name while the previous "
                "release is still querying it."
            )
            safe = (
                f"Create {new_name} alongside {table}, dual-write, backfill, switch reads, "
                f"then drop {table} in a later migration under an MG004 allow."
            )
        else:
            column = op.column or "the column"
            message = (
                f"Renaming {table}.{column} to {new_name} removes the old name while the "
                "previous release is still selecting it."
            )
            safe = (
                f"Add {new_name} as a new column, write both names, backfill in batches, "
                f"switch reads, then drop {column} in a later migration under an MG004 allow."
            )
        return Finding(
            code=self.code,
            severity=self.severity,
            span=op.span,
            table=op.table,
            message=message,
            safe_alternative=safe,
            statement=op.raw,
        )


RULE = MG005()
