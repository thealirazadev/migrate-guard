"""MG008 - enum value removal or redefinition.

A heuristic, and the message says so. migrate-guard reads one migration file and
never connects to a database, so it cannot know the enum's previous member list;
schema diffing is a non-goal. What it can see is the two statements that make a
removal possible, and both are worth a human look.

MySQL: any MODIFY/CHANGE to ENUM(...) restates the whole member list. Dropping or
reordering a member there copies the table and silently remaps rows by ordinal.
Postgres: DROP TYPE is the first half of the drop-and-recreate pattern people
reach for when they want to remove a value.

Severity is warning, not error: the safe case (appending a member) is common and
should not gate CI on its own.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..config import Config
from ..ir import Finding, Operation, OpKind


class MG008:
    code = "MG008"
    severity = "warning"
    dialects = ("postgres", "mysql")
    summary = "enum value removal or redefinition"
    explanation = """MG008 fires on a MySQL enum redefinition and on a Postgres DROP TYPE.

migrate-guard analyses one file at a time and never reads a live schema, so it
cannot tell an appended enum member from a removed one. Rather than guess, it
reports the statements where a removal can hide and says why.

MySQL. ALTER TABLE ... MODIFY col ENUM(...) restates the entire member list:

    ALTER TABLE orders MODIFY status ENUM('new', 'paid');

If 'refunded' was in the old list, every row holding it becomes an invalid value or
an empty string, and any reordering silently remaps rows, because MySQL stores the
ordinal and not the text. The statement also copies the table. Appending a member at
the end of the list is the one cheap case: it is an in-place metadata change.

Postgres. DROP TYPE is the first step of drop-and-recreate, the usual way people
try to remove a value:

    DROP TYPE order_status;

Adding a value is safe and needs no such dance:

    ALTER TYPE order_status ADD VALUE 'refunded';

Removing one has no direct support. The safe route is a new type, a column swap, and
a drop of the old type once nothing references it, each in its own migration.

Because a removal cannot be distinguished from an append here, MG008 is a warning:
it does not gate a build unless fail_on = "warning". Confirm the member list against
the previous schema, then suppress the occurrence with a reason:

    -- migrate-guard: allow MG008 reason="appends 'refunded', no member removed"
"""

    def check(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None:
        if config.dialect == "mysql" and op.kind is OpKind.redefine_enum:
            table = op.table or "the table"
            column = op.column or "the column"
            return _finding(
                self,
                op,
                (
                    f"Redefining the enum on {table}.{column} restates the whole member "
                    "list; migrate-guard cannot see the previous one, so a removal or "
                    "reorder would be invisible here."
                ),
                (
                    "Confirm against the previous schema that this only appends members at "
                    "the end of the list. To remove one, add a replacement column, migrate "
                    "the values in batches, then drop the old column."
                ),
            )
        if config.dialect == "postgres" and op.kind is OpKind.drop_type:
            target = op.table or "the type"
            return _finding(
                self,
                op,
                (
                    f"DROP TYPE {target} is the drop-and-recreate pattern used to remove "
                    "enum values, which loses every row still holding a removed member."
                ),
                (
                    "To add a member use ALTER TYPE ... ADD VALUE. To remove one, create a "
                    "new type, swap the column over in batches, and drop the old type in a "
                    "later migration once nothing references it."
                ),
            )
        return None


def _finding(rule: MG008, op: Operation, message: str, safe_alternative: str) -> Finding:
    return Finding(
        code=rule.code,
        severity=rule.severity,
        span=op.span,
        table=op.table,
        message=message,
        safe_alternative=safe_alternative,
        statement=op.raw,
    )


RULE = MG008()
