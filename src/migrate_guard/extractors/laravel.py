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

from ..ir import Finding, Operation, OpKind, SourceSpan, excerpt
from ..rules import mg000
from . import ExtractionResult
from .sql import extract as extract_sql

# Regex for schema builder calls
SCHEMA_DROP = re.compile(
    r"Schema::(drop|dropIfExists)\s*\(",
    re.IGNORECASE,
)
SCHEMA_TABLE = re.compile(
    r"Schema::table\s*\(",
    re.IGNORECASE,
)
SCHEMA_CREATE = re.compile(
    r"Schema::create\s*\(",
    re.IGNORECASE,
)
SCHEMA_RENAME = re.compile(
    r"Schema::rename\s*\(",
    re.IGNORECASE,
)
DB_STATEMENT = re.compile(
    r"DB::(statement|unprepared)\s*\(",
    re.IGNORECASE,
)
# Column-level operations inside Schema::table closures
DROP_COLUMN = re.compile(
    r"\->dropColumn\s*\(",
    re.IGNORECASE,
)
RENAME_COLUMN = re.compile(
    r"\->renameColumn\s*\(",
    re.IGNORECASE,
)
CREATE_INDEX = re.compile(
    r"\->(?:index|unique)\s*\(",
    re.IGNORECASE,
)


def extract(path: str, text: str, dialect: str) -> ExtractionResult:
    """Map one Laravel migration file to operations plus MG000 diagnostics."""
    # Strip comments and string contents to avoid false positives
    cleaned = _strip_comments_and_strings(text)

    operations: list[Operation] = []
    diagnostics: list[Finding] = []

    # Find all Schema::drop calls
    for match in SCHEMA_DROP.finditer(cleaned):
        line = _line_number(match.start(), cleaned)
        raw_excerpt = _extract_raw_excerpt(text, match.start(), line)
        span = SourceSpan(file=path, line=line)
        operations.append(Operation(kind=OpKind.drop_table, span=span, raw=raw_excerpt))

    # Find all Schema::table calls and extract operations from closures
    for match in SCHEMA_TABLE.finditer(cleaned):
        line = _line_number(match.start(), cleaned)
        raw_excerpt = _extract_raw_excerpt(text, match.start(), line)
        span = SourceSpan(file=path, line=line)

        # Find the closure content (between { and })
        closure_start = cleaned.find("{", match.end())
        if closure_start != -1:
            closure_end = _find_matching_brace(cleaned, closure_start)
            if closure_end != -1:
                closure_content = cleaned[closure_start : closure_end + 1]

                # Find dropColumn calls
                for drop_match in DROP_COLUMN.finditer(closure_content):
                    drop_line = line + closure_content[: drop_match.start()].count("\n")
                    drop_span = SourceSpan(file=path, line=drop_line)
                    drop_raw = _extract_raw_excerpt(
                        text, closure_start + drop_match.start(), drop_line
                    )
                    operations.append(
                        Operation(kind=OpKind.drop_column, span=drop_span, raw=drop_raw)
                    )

                # Find renameColumn calls
                for rename_match in RENAME_COLUMN.finditer(closure_content):
                    rename_line = line + closure_content[: rename_match.start()].count("\n")
                    rename_span = SourceSpan(file=path, line=rename_line)
                    rename_raw = _extract_raw_excerpt(
                        text, closure_start + rename_match.start(), rename_line
                    )
                    operations.append(
                        Operation(kind=OpKind.rename_column, span=rename_span, raw=rename_raw)
                    )

                # Find create index calls
                for index_match in CREATE_INDEX.finditer(closure_content):
                    index_line = line + closure_content[: index_match.start()].count("\n")
                    index_span = SourceSpan(file=path, line=index_line)
                    index_raw = _extract_raw_excerpt(
                        text, closure_start + index_match.start(), index_line
                    )
                    operations.append(
                        Operation(
                            kind=OpKind.create_index,
                            span=index_span,
                            raw=index_raw,
                            details={
                                "unique": "unique" in index_match.group(0).lower(),
                                "concurrent": False,
                            },
                        )
                    )

    # Find all Schema::create calls
    for match in SCHEMA_CREATE.finditer(cleaned):
        line = _line_number(match.start(), cleaned)
        raw_excerpt = _extract_raw_excerpt(text, match.start(), line)
        span = SourceSpan(file=path, line=line)
        operations.append(Operation(kind=OpKind.create_table, span=span, raw=raw_excerpt))

    # Find all Schema::rename calls
    for match in SCHEMA_RENAME.finditer(cleaned):
        line = _line_number(match.start(), cleaned)
        raw_excerpt = _extract_raw_excerpt(text, match.start(), line)
        span = SourceSpan(file=path, line=line)
        operations.append(Operation(kind=OpKind.rename_table, span=span, raw=raw_excerpt))

    # Find all DB::statement and DB::unprepared calls with SQL literals
    for match in DB_STATEMENT.finditer(cleaned):
        line = _line_number(match.start(), cleaned)

        # Try to extract the literal argument
        literal = _extract_literal_argument(cleaned, match.end())
        if literal is None:
            # Variable argument - cannot extract
            span = SourceSpan(file=path, line=line)
            raw = _extract_raw_excerpt(text, match.start(), line)
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


def _line_number(pos: int, text: str) -> int:
    """Get 1-based line number for a position in text."""
    return text[:pos].count("\n") + 1


def _extract_raw_excerpt(text: str, pos: int, line: int) -> str:
    """Extract a raw excerpt from the file at the given line."""
    lines = text.split("\n")
    if line <= len(lines):
        return excerpt(lines[line - 1])
    return excerpt(text)


def _find_matching_brace(text: str, start: int) -> int:
    """Find the closing brace matching the opening brace at start."""
    if start >= len(text) or text[start] != "{":
        return -1

    count = 1
    i = start + 1
    in_string = False
    string_char = None

    while i < len(text) and count > 0:
        char = text[i]

        # Handle strings
        if char in ('"', "'") and (i == 0 or text[i - 1] != "\\"):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None

        # Count braces only outside strings
        if not in_string:
            if char == "{":
                count += 1
            elif char == "}":
                count -= 1

        i += 1

    return i - 1 if count == 0 else -1


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
