"""Frozen data contract shared by extractors, the engine, and the reporters.

Field names are fixed by docs/architecture.md and must not be renamed: the JSON
reporter and the config surface are part of the tool's public contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

RAW_EXCERPT_LIMIT = 200


class OpKind(StrEnum):
    """Normalized migration operations produced by every extractor."""

    create_table = "create_table"
    add_column = "add_column"
    alter_column_type = "alter_column_type"
    set_not_null = "set_not_null"
    add_check_not_valid = "add_check_not_valid"
    validate_constraint = "validate_constraint"
    drop_column = "drop_column"
    drop_table = "drop_table"
    rename_column = "rename_column"
    rename_table = "rename_table"
    create_index = "create_index"
    add_foreign_key = "add_foreign_key"
    add_unique_constraint = "add_unique_constraint"
    drop_type = "drop_type"
    redefine_enum = "redefine_enum"
    dml = "dml"
    other_ddl = "other_ddl"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Where an operation or comment sits: the path as given, 1-based line."""

    file: str
    line: int


@dataclass(frozen=True, slots=True)
class Operation:
    kind: OpKind
    span: SourceSpan
    raw: str
    table: str | None = None
    column: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Allow:
    """A waiver for one or more rule codes with a mandatory justification."""

    codes: tuple[str, ...]
    reason: str
    span: SourceSpan
    source: str


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: str
    span: SourceSpan
    message: str
    safe_alternative: str
    statement: str
    table: str | None = None
    allowed: bool = False
    allow_reason: str | None = None


def excerpt(text: str) -> str:
    """Collapse a statement to one line and cap it at the documented 200 chars."""
    flat = " ".join(text.split())
    if len(flat) <= RAW_EXCERPT_LIMIT:
        return flat
    return flat[:RAW_EXCERPT_LIMIT]
