"""MG004 - DROP COLUMN and DROP TABLE.

Destruction is irreversible and the previous application version may still be
reading what is being removed. MG004 always fires; the only waiver is an inline
allow at the drop site, because the justification belongs in the diff the
reviewer is reading. Config ignore refuses MG004 at load time.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..config import Config
from ..ir import Finding, Operation, OpKind

DROP_KINDS = (OpKind.drop_column, OpKind.drop_table)


class MG004:
    code = "MG004"
    severity = "error"
    dialects = ("postgres", "mysql")
    summary = "DROP COLUMN / DROP TABLE (inline allow required)"
    explanation = """MG004 fires on every DROP COLUMN and DROP TABLE.

The data is gone the moment the migration commits, and during a rolling deploy the
previous application version is still selecting the column or table. A drop that
races the deploy window turns into errors on live traffic, and the only recovery is
a restore.

Unsafe:

    ALTER TABLE users DROP COLUMN legacy_flag;
    DROP TABLE audit_legacy;

Safe sequence: stop writing the column or table, ship that version, confirm nothing
reads it (log or pg_stat_user_tables), then drop it in a later migration once the old
version is fully retired. On Postgres, DROP COLUMN itself is metadata-only and fast;
the danger is the data loss and the deploy window, not the lock.

MG004 cannot be ignored globally. Waive one drop with an inline allow that records
who approved it:

    -- migrate-guard: allow MG004 reason="audit_legacy retired 2026-06, approved OPS-1123"
"""

    def check(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None:
        if op.kind not in DROP_KINDS:
            return None
        if op.kind is OpKind.drop_table:
            target = op.table or "the table"
            message = f"DROP TABLE removes {target} and its data permanently."
            safe = (
                f"Stop reading and writing {target}, ship that version, then drop it in a "
                "later migration once the previous release is retired."
            )
        else:
            column = op.column or "the column"
            target = op.table or "the table"
            message = (
                f"DROP COLUMN removes {column} from {target} permanently, and the previous "
                "release may still read it."
            )
            safe = (
                f"Stop writing {column}, ship that version, then drop it in a later "
                "migration once no running code selects it."
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


RULE = MG004()
