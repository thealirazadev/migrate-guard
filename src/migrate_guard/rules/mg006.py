"""MG006 - a foreign key added with immediate validation (Postgres).

ADD CONSTRAINT ... FOREIGN KEY takes SHARE ROW EXCLUSIVE on the referencing
table and ROW SHARE on the referenced one, then scans every existing row to
prove the constraint holds. Both tables block writes for the length of that
scan. NOT VALID skips the scan; a later VALIDATE CONSTRAINT does the checking
under SHARE UPDATE EXCLUSIVE, which lets writes through.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..config import Config
from ..ir import Finding, Operation, OpKind


class MG006:
    code = "MG006"
    severity = "error"
    dialects = ("postgres",)
    summary = "foreign key added with immediate validation"
    explanation = """MG006 fires on ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY without
NOT VALID.

Adding the constraint the plain way locks the referencing table with SHARE ROW
EXCLUSIVE and the referenced table with ROW SHARE, then reads every row of the
referencing table to prove no orphan exists. Writes to both tables wait for that
scan, which on a large table is minutes.

Unsafe:

    ALTER TABLE orders ADD CONSTRAINT orders_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id);

Safe, in two migrations:

    -- 1. the constraint applies to new and changed rows immediately, no scan
    ALTER TABLE orders ADD CONSTRAINT orders_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;

    -- 2. later, validate the existing rows under SHARE UPDATE EXCLUSIVE
    ALTER TABLE orders VALIDATE CONSTRAINT orders_user_fk;

Clean up any orphan rows before step 2, or the validation fails and has to be
repeated. VALIDATE CONSTRAINT on its own is never a finding.

Suppress one occurrence with an inline allow carrying a reason:

    -- migrate-guard: allow MG006 reason="orders is empty in every environment"
"""

    def check(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None:
        if op.kind is not OpKind.add_foreign_key or op.details.get("not_valid"):
            return None
        table = op.table or "the table"
        return Finding(
            code=self.code,
            severity=self.severity,
            span=op.span,
            table=op.table,
            message=(
                f"Adding a foreign key to {table} without NOT VALID scans every existing "
                "row and blocks writes to both tables while it runs."
            ),
            safe_alternative=(
                "Add the constraint with NOT VALID now, then run ALTER TABLE "
                f"{table} VALIDATE CONSTRAINT <name>; in a later migration, which takes "
                "only SHARE UPDATE EXCLUSIVE."
            ),
            statement=op.raw,
        )


RULE = MG006()
