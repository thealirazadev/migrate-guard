"""MG001 - an ALTER that rewrites the table or scans it under a blocking lock.

Three Postgres shapes and one MySQL shape share this code because they share one
consequence: the table is unavailable for the duration.

(a) ALTER COLUMN ... TYPE rewrites every row under ACCESS EXCLUSIVE unless the
    change is one of the widenings Postgres records as metadata only.
(b) ADD COLUMN ... DEFAULT rewrote the whole table before Postgres 11. From 11 a
    constant default is stored as a "missing value" and costs nothing, but a
    volatile default still has to be evaluated per row, so it still rewrites.
(c) SET NOT NULL takes ACCESS EXCLUSIVE and scans the table to prove no NULL
    exists. Postgres 12 skips that scan when an already-validated
    CHECK (col IS NOT NULL) proves it, so the same-file sequence is exempt.

MySQL copies the table for almost every type change; only widening a VARCHAR
inside the same length-prefix class is done in place.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from ..config import Config
from ..ir import Finding, Operation, OpKind

DEFAULT_ON_ADD_COLUMN_VERSION = 11
NOT_NULL_CHECK_VERSION = 12
# MySQL stores a VARCHAR length prefix of one byte while the column holds at
# most 255 bytes. Assuming utf8mb4 (four bytes per character, the modern
# default) that boundary sits at 63 characters; crossing it rebuilds the table.
MYSQL_ONE_BYTE_PREFIX_LIMIT = 63

TYPE_PATTERN = re.compile(r"^\s*(?P<name>[a-z][a-z0-9 _]*?)\s*(?:\(\s*(?P<params>[\d,\s]+)\))?\s*$")
VARCHAR_TYPES = ("varchar", "character varying")
NUMERIC_TYPES = ("numeric", "decimal")
VARBIT_TYPES = ("varbit", "bit varying")


class MG001:
    code = "MG001"
    severity = "error"
    dialects = ("postgres", "mysql")
    summary = "ALTER that rewrites or scan-locks the table"
    explanation = """MG001 fires on an ALTER TABLE that rewrites the table or scans it
while holding a lock that blocks reads and writes.

Postgres, three forms:

1. ALTER COLUMN ... TYPE. Changing a column's type rewrites every row under ACCESS
   EXCLUSIVE, which blocks even SELECT. Postgres skips the rewrite only for a few
   widenings: varchar(n) to a longer varchar or to text, numeric(p,s) to a larger
   precision at the same scale, and varbit widening. migrate-guard cannot see the
   old type from a single migration file, so it reports every type change and
   leaves the widening case to an inline allow.

2. ADD COLUMN ... DEFAULT on PostgreSQL 10 and earlier. The default had to be
   written into every existing row, rewriting the table. From PostgreSQL 11 a
   constant default is recorded once as a missing value and the statement is
   metadata-only, so migrate-guard stays silent there. A volatile default such as
   now() or gen_random_uuid() must be evaluated per row and still rewrites, on
   every version.

3. SET NOT NULL. It takes ACCESS EXCLUSIVE and scans the whole table to prove no
   NULL exists. PostgreSQL 12 and later skip the scan when a validated
   CHECK (col IS NOT NULL) already proves it, so this sequence is safe and
   migrate-guard suppresses the finding when it sees it in the same file:

    ALTER TABLE users ADD CONSTRAINT users_email_nn CHECK (email IS NOT NULL) NOT VALID;
    ALTER TABLE users VALIDATE CONSTRAINT users_email_nn;
    ALTER TABLE users ALTER COLUMN email SET NOT NULL;

MySQL: MODIFY and CHANGE copy the whole table under a metadata lock for nearly every
type change. Widening a VARCHAR without crossing its length-prefix boundary is done
in place; everything else should go through a new column, a batched backfill, and a
rename, or through an online schema change tool.

Suppress one occurrence with an inline allow carrying a reason:

    -- migrate-guard: allow MG001 reason="table has 400 rows, rewrite is instant"
"""

    def check(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None:
        if op.kind is OpKind.alter_column_type:
            return self._type_change(op, config)
        if config.dialect != "postgres":
            return None
        if op.kind is OpKind.add_column:
            return self._added_default(op, config)
        if op.kind is OpKind.set_not_null:
            return self._not_null(op, file_ops, index, config)
        return None

    def _type_change(self, op: Operation, config: Config) -> Finding | None:
        old_type = op.details.get("old_type")
        new_type = op.details.get("new_type")
        if _is_safe_widening(old_type, new_type, config.dialect):
            return None
        target = _target(op)
        if config.dialect == "postgres":
            message = (
                f"Changing the type of {target} rewrites the whole table under an "
                "ACCESS EXCLUSIVE lock, which blocks reads as well as writes."
            )
        else:
            message = (
                f"MODIFY or CHANGE on {target} copies the whole table while holding a "
                "metadata lock, so writes queue behind it."
            )
        return _finding(self, op, message, _NEW_COLUMN_DANCE.format(target=target))

    def _added_default(self, op: Operation, config: Config) -> Finding | None:
        if not op.details.get("has_default"):
            return None
        target = _target(op)
        if config.postgres_version < DEFAULT_ON_ADD_COLUMN_VERSION:
            return _finding(
                self,
                op,
                f"ADD COLUMN {target} with a DEFAULT rewrites every existing row on "
                f"PostgreSQL {config.postgres_version}.",
                (
                    f"Add the column with no default, then set it separately: ALTER TABLE "
                    f"{_table(op)} ALTER COLUMN {_column(op)} SET DEFAULT ...; and backfill "
                    "existing rows in batches."
                ),
            )
        if op.details.get("default_volatile"):
            return _finding(
                self,
                op,
                f"ADD COLUMN {target} with a volatile DEFAULT is evaluated per row, so it "
                "rewrites the whole table even on PostgreSQL 11 and later.",
                (
                    f"Add the column with no default, backfill it in batches, then run "
                    f"ALTER TABLE {_table(op)} ALTER COLUMN {_column(op)} SET DEFAULT ...; "
                    "for new rows."
                ),
            )
        return None

    def _not_null(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None:
        if config.postgres_version >= NOT_NULL_CHECK_VERSION and _check_validated(
            op, file_ops, index
        ):
            return None
        target = _target(op)
        if config.postgres_version >= NOT_NULL_CHECK_VERSION:
            safe = (
                f"Add CHECK ({_column(op)} IS NOT NULL) NOT VALID, VALIDATE CONSTRAINT it in "
                f"a later migration, then SET NOT NULL: PostgreSQL {config.postgres_version} "
                "skips the scan when a validated check already proves it."
            )
        else:
            safe = (
                f"Backfill {_column(op)} in batches and enforce it in the application, or "
                "take the write outage deliberately in a maintenance window; the scan-free "
                "CHECK sequence needs PostgreSQL 12 or later."
            )
        return _finding(
            self,
            op,
            f"SET NOT NULL on {target} takes ACCESS EXCLUSIVE and scans every row before "
            "it returns.",
            safe,
        )


_NEW_COLUMN_DANCE = (
    "Add a new column of the target type, backfill it in batches, switch the application "
    "over, then drop the old one; {target} stays readable throughout."
)


def _check_validated(op: Operation, file_ops: Sequence[Operation], index: int) -> bool:
    """True when this file already added and validated CHECK (col IS NOT NULL)."""
    table = _key(op.table)
    column = _key(op.column)
    for position, earlier in enumerate(file_ops[:index]):
        if earlier.kind is not OpKind.add_check_not_valid:
            continue
        if _key(earlier.table) != table or _key(earlier.column) != column:
            continue
        name = _key(earlier.details.get("constraint"))
        for later in file_ops[position + 1 : index]:
            if later.kind is not OpKind.validate_constraint or _key(later.table) != table:
                continue
            if name is None or _key(later.details.get("constraint")) == name:
                return True
    return False


def _is_safe_widening(old_type: str | None, new_type: str | None, dialect: str) -> bool:
    """Widenings the engine records as metadata only. Unknown old type is never safe."""
    old = _parse_type(old_type)
    new = _parse_type(new_type)
    if old is None or new is None:
        return False
    old_name, old_params = old
    new_name, new_params = new

    if old_name in VARCHAR_TYPES and new_name in VARCHAR_TYPES:
        return _wider(old_params, new_params, dialect)
    if dialect != "postgres":
        return False
    if old_name in VARCHAR_TYPES and new_name == "text":
        return True
    if old_name in NUMERIC_TYPES and new_name in NUMERIC_TYPES:
        return (
            len(old_params) == 2
            and len(new_params) == 2
            and old_params[1] == new_params[1]
            and new_params[0] > old_params[0]
        )
    if old_name in VARBIT_TYPES and new_name in VARBIT_TYPES:
        return _wider(old_params, new_params, dialect)
    return False


def _wider(old_params: tuple[int, ...], new_params: tuple[int, ...], dialect: str) -> bool:
    if not new_params:
        return dialect == "postgres" and bool(old_params)
    if not old_params or new_params[0] <= old_params[0]:
        return False
    if dialect == "postgres":
        return True
    return (old_params[0] <= MYSQL_ONE_BYTE_PREFIX_LIMIT) == (
        new_params[0] <= MYSQL_ONE_BYTE_PREFIX_LIMIT
    )


def _parse_type(text: str | None) -> tuple[str, tuple[int, ...]] | None:
    if not text:
        return None
    match = TYPE_PATTERN.match(text.strip().lower())
    if match is None:
        return None
    raw = match["params"]
    params = tuple(int(part) for part in raw.split(",")) if raw else ()
    return " ".join(match["name"].split()), params


def _finding(rule: MG001, op: Operation, message: str, safe_alternative: str) -> Finding:
    return Finding(
        code=rule.code,
        severity=rule.severity,
        span=op.span,
        table=op.table,
        message=message,
        safe_alternative=safe_alternative,
        statement=op.raw,
    )


def _target(op: Operation) -> str:
    return f"{_table(op)}.{_column(op)}" if op.column else _table(op)


def _table(op: Operation) -> str:
    return op.table or "the table"


def _column(op: Operation) -> str:
    return op.column or "the column"


def _key(value: str | None) -> str | None:
    return value.casefold() if isinstance(value, str) else None


RULE = MG001()
