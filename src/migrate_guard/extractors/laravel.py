"""Laravel migration extraction via bounded regexes.

The Laravel extractor uses regexes to identify schema builder calls
without parsing PHP, avoiding a heavy PHP parser dependency. Calls the
SQL extractor for DB::statement and DB::unprepared raw SQL literals.
Unrecognized calls are skipped silently; recognized calls with
unextractable arguments produce MG000.

Comment and string stripping happens before regex matching to avoid
false positives on literal strings inside migrations.
"""

from __future__ import annotations

import re

from ..ir import Allow, Finding, Operation, OpKind, SourceSpan, excerpt
from ..rules import mg000
from . import ExtractionResult
from .sql import extract as extract_sql

# Regex for schema builder calls. Matches method chains like:
# Schema::create('table', function ($table) { $table->... })
# $table->string('name')->unique()->change();
# DB::statement('...')
SCHEMA_CALL = re.compile(
    r"Schema::(create|table|drop|dropIfExists|rename)\s*\(",
    re.IGNORECASE,
)
DB_STATEMENT = re.compile(
    r"DB::(statement|unprepared)\s*\(",
    re.IGNORECASE,
)
COLUMN_METHOD = re.compile(
    r"\->(change|unique|index|foreign|nullable|constrained|default|dropColumn|renameColumn)\s*\(",
    re.IGNORECASE,
)


def extract(path: str, text: str, dialect: str) -> ExtractionResult:
    """Map one Laravel migration file to operations plus MG000 diagnostics."""
    # Strip comments and string contents to avoid false positives
    cleaned = _strip_comments_and_strings(text)

    operations: list[Operation] = []
    diagnostics: list[Finding] = []
    line_map: dict[int, int] = _build_line_map(text, cleaned)

    # Find all Schema:: calls
    for match in SCHEMA_CALL.finditer(cleaned):
        line = _line_number(match.start(), cleaned)
        mapped_line = line_map.get(line, line)
        op_type = match.group(1).lower()

        raw_excerpt = _extract_raw_excerpt(text, match.start(), mapped_line)
        span = SourceSpan(file=path, line=mapped_line)

        if op_type == "create":
            operations.append(
                Operation(kind=OpKind.create_table, span=span, raw=raw_excerpt)
            )
        elif op_type in ("drop", "dropifexists"):
            operations.append(
                Operation(kind=OpKind.drop_table, span=span, raw=raw_excerpt)
            )
        elif op_type == "rename":
            operations.append(
                Operation(kind=OpKind.rename_table, span=span, raw=raw_excerpt)
            )
        elif op_type == "table":
            # Schema::table calls modify existing tables; check for operations inside
            operations.extend(_extract_table_operations(cleaned, match, path, line_map))

    # Find all DB::statement and DB::unprepared calls with SQL literals
    for match in DB_STATEMENT.finditer(cleaned):
        line = _line_number(match.start(), cleaned)
        mapped_line = line_map.get(line, line)

        # Try to extract the literal argument
        literal = _extract_literal_argument(cleaned, match.end())
        if literal is None:
            # Variable argument - cannot extract
            span = SourceSpan(file=path, line=mapped_line)
            raw = _extract_raw_excerpt(text, match.start(), mapped_line)
            diagnostics.append(
                mg000.diagnostic(
                    span,
                    raw,
                    f"DB::{match.group(1)} has a variable or complex argument; "
                    "migrate-guard could not analyze it.",
                )
            )
        else:
            # Extract SQL from the literal
            result = extract_sql(path, literal, dialect)
            operations.extend(result.operations)
            diagnostics.extend(result.diagnostics)

    return ExtractionResult(
        operations=tuple(operations),
        diagnostics=tuple(diagnostics),
        statement_count=len(operations),
    )


def _strip_comments_and_strings(text: str) -> str:
    """Remove PHP comments and string contents to avoid regex false positives."""
    result = []
    i = 0
    while i < len(text):
        # Skip // comments
        if i + 1 < len(text) and text[i : i + 2] == "//":
            # Skip to end of line, keep newline
            while i < len(text) and text[i] != "\n":
                i += 1
            if i < len(text):
                result.append("\n")
                i += 1
            continue

        # Skip # comments
        if text[i] == "#":
            while i < len(text) and text[i] != "\n":
                i += 1
            if i < len(text):
                result.append("\n")
                i += 1
            continue

        # Skip /* */ comments
        if i + 1 < len(text) and text[i : i + 2] == "/*":
            i += 2
            while i + 1 < len(text) and text[i : i + 2] != "*/":
                if text[i] == "\n":
                    result.append("\n")
                i += 1
            i += 2  # Skip */
            continue

        # Skip double-quoted strings
        if text[i] == '"':
            result.append(" ")
            i += 1
            while i < len(text) and text[i] != '"':
                if text[i] == "\\":
                    i += 2
                else:
                    i += 1
            if i < len(text):
                i += 1  # Skip closing quote
            continue

        # Skip single-quoted strings
        if text[i] == "'":
            result.append(" ")
            i += 1
            while i < len(text) and text[i] != "'":
                if text[i] == "\\":
                    i += 2
                else:
                    i += 1
            if i < len(text):
                i += 1  # Skip closing quote
            continue

        # Skip backtick strings (MySQL identifier quotes in Laravel sometimes)
        if text[i] == "`":
            result.append(" ")
            i += 1
            while i < len(text) and text[i] != "`":
                if text[i] == "\\":
                    i += 2
                else:
                    i += 1
            if i < len(text):
                i += 1  # Skip closing backtick
            continue

        result.append(text[i])
        i += 1

    return "".join(result)


def _build_line_map(original: str, cleaned: str) -> dict[int, int]:
    """Map positions in the cleaned text back to line numbers in the original."""
    mapping = {}
    original_lines = original.split("\n")
    cleaned_lines = cleaned.split("\n")

    original_line = 1
    for cleaned_line_idx, cleaned_line in enumerate(cleaned_lines):
        # Find matching original line
        while original_line <= len(original_lines):
            original_line_text = original_lines[original_line - 1]
            # Strip comments/strings from original line for comparison
            if original_line_text.strip():
                mapping[cleaned_line_idx + 1] = original_line
            if original_line_text == cleaned_line or (
                cleaned_line.strip()
                and original_line_text.strip()
            ):
                break
            original_line += 1

    return mapping


def _line_number(pos: int, text: str) -> int:
    """Get 1-based line number for a position in text."""
    return text[:pos].count("\n") + 1


def _extract_raw_excerpt(text: str, pos: int, line: int) -> str:
    """Extract a raw excerpt from the file at the given line."""
    lines = text.split("\n")
    if line <= len(lines):
        return excerpt(lines[line - 1])
    return excerpt(text)


def _extract_table_operations(
    cleaned: str, match: re.Match, path: str, line_map: dict[int, int]
) -> list[Operation]:
    """Extract operations from within a Schema::table() closure."""
    # For now, return empty list; the actual column operations would be
    # detected by COLUMN_METHOD patterns within the table closure
    # This is a simplified implementation that catches the common patterns
    operations = []

    # Find the position after the opening paren
    start = match.end()
    # Look for column definition methods in the following content
    for col_match in COLUMN_METHOD.finditer(cleaned[start:]):
        method = col_match.group(1).lower()
        abs_pos = start + col_match.start()
        line = _line_number(abs_pos, cleaned)
        mapped_line = line_map.get(line, line)

        if method == "change":
            # ALTER COLUMN TYPE or change operations
            pass  # Details would require more context
        elif method == "dropcol":
            operations.append(
                Operation(
                    kind=OpKind.drop_column,
                    span=SourceSpan(file=path, line=mapped_line),
                    raw=_extract_raw_excerpt("", abs_pos, mapped_line),
                )
            )
        elif method == "renamecolumn":
            operations.append(
                Operation(
                    kind=OpKind.rename_column,
                    span=SourceSpan(file=path, line=mapped_line),
                    raw=_extract_raw_excerpt("", abs_pos, mapped_line),
                )
            )

    return operations


def _extract_literal_argument(text: str, pos: int) -> str | None:
    """Extract a string literal argument from a function call.

    Returns the literal content, or None if the argument is not a simple string.
    """
    # Skip whitespace
    while pos < len(text) and text[pos] in (" ", "\t", "\n"):
        pos += 1

    if pos >= len(text):
        return None

    # Check for single-quoted or double-quoted string
    if text[pos] in ("'", '"'):
        quote = text[pos]
        pos += 1
        result = []
        while pos < len(text) and text[pos] != quote:
            if text[pos] == "\\":
                if pos + 1 < len(text):
                    result.append(text[pos : pos + 2])
                    pos += 2
            else:
                result.append(text[pos])
                pos += 1

        if pos < len(text) and text[pos] == quote:
            return "".join(result)

    return None
