"""MG003 - ADD COLUMN NOT NULL with no default and no backfill.

On a table that already has rows the statement simply fails: there is no value
to put in the existing rows. On an empty table it succeeds and then breaks the
previous application version, which still inserts without the column.

The neighbouring case, a NOT NULL column added *with* a default, is not MG003:
it is safe on PostgreSQL 11 and later and on MySQL 8.0, and on PostgreSQL 10 and
earlier it is MG001 because the default rewrites the table.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..config import Config
from ..ir import Finding, Operation, OpKind


class MG003:
    code = "MG003"
    severity = "error"
    dialects = ("postgres", "mysql")
    summary = "NOT NULL column added without default or backfill"
    explanation = """MG003 fires on ADD COLUMN ... NOT NULL when the statement carries no
DEFAULT.

Existing rows have no value for the new column, so the ALTER fails outright on any
non-empty table. When the table happens to be empty the statement succeeds, and the
release still running the previous code keeps inserting rows without the column,
which now fails on every insert.

Unsafe:

    ALTER TABLE users ADD COLUMN email text NOT NULL;

Safe, in three migrations:

    -- 1. add it nullable, deploy the code that writes it
    ALTER TABLE users ADD COLUMN email text;

    -- 2. backfill in batches, for example
    UPDATE users SET email = '' WHERE email IS NULL AND id BETWEEN 1 AND 10000;

    -- 3. enforce it without the full-table scan (PostgreSQL 12+)
    ALTER TABLE users ADD CONSTRAINT users_email_nn CHECK (email IS NOT NULL) NOT VALID;
    ALTER TABLE users VALIDATE CONSTRAINT users_email_nn;
    ALTER TABLE users ALTER COLUMN email SET NOT NULL;

A single statement with a constant default is also safe on PostgreSQL 11 and later
and on MySQL 8.0, and migrate-guard stays silent on it:

    ALTER TABLE users ADD COLUMN email text NOT NULL DEFAULT '';

Suppress one occurrence with an inline allow carrying a reason:

    -- migrate-guard: allow MG003 reason="users is empty until the next release"
"""

    def check(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None:
        if op.kind is not OpKind.add_column:
            return None
        if not op.details.get("not_null") or op.details.get("has_default"):
            return None
        table = op.table or "the table"
        column = op.column or "the column"
        return Finding(
            code=self.code,
            severity=self.severity,
            span=op.span,
            table=op.table,
            message=(
                f"ADD COLUMN {column} NOT NULL without a DEFAULT fails on {table} as soon "
                "as it holds a single row."
            ),
            safe_alternative=(
                f"Add {column} nullable, backfill it in batches, then enforce it with "
                f"CHECK ({column} IS NOT NULL) NOT VALID, VALIDATE CONSTRAINT, and "
                "SET NOT NULL; or give this statement a constant DEFAULT."
            ),
            statement=op.raw,
        )


RULE = MG003()
